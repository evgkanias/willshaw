import numpy as np
import numpy.linalg as la
from datetime import datetime
from PIL import ImageDraw, Image
from colorsys import hsv_to_rgb
from utils import vec2sph
from ephem import Observer
from sky import get_seville_observer, ChromaticitySkyModel
from compoundeye import CompoundEye
from geometry import PolygonList, Route

WIDTH = 36
HEIGHT = 10
LENGTH = 36

GRASS_COLOUR = (0, 255, 0)
GROUND_COLOUR = (229, 183, 90)
SKY_COLOUR = (13, 135, 201)


class World(object):
    """
    A representation of the world with object (described as polygons) and agents' routes
    """

    def __init__(self, observer=None, polygons=None, width=WIDTH, length=LENGTH, height=HEIGHT,
                 uniform_sky=False, enable_pol_filters=True):
        """
        Creates a world.

        :param observer: a reference to an observer
        :type observer: Observer
        :param polygons: polygons of the objects in the world
        :type polygons: PolygonList
        :param width: the width of the world
        :type width: int
        :param length: the length of the world
        :type length: int
        :param height: the height of the world
        :type height: int
        :param uniform_sky: flag that indicates if there is a uniform sky or not
        :type uniform_sky: bool
        :param enable_pol_filters: flag to switch on/off the POL filters of the eyes
        :type enable_pol_filters: bool
        """
        # normalise world
        xmax = np.array([polygons.x.max(), polygons.y.max(), polygons.z.max()]).max()

        # default observer is in Seville (where the data come from)
        if observer is None:
            observer = get_seville_observer()
        observer.date = datetime.now()

        # create and generate a sky instance
        self.sky = ChromaticitySkyModel(observer=observer, nside=1)
        self.sky.generate()

        # create a compound eye model for the sky pixels
        self.eye = None  # type: CompoundEye
        self.__pol_filters = enable_pol_filters

        # store the polygons and initialise the parameters
        self.polygons = polygons
        self.routes = []
        self.width = width
        self.length = length
        self.height = height
        self.__normalise_factor = xmax  # type: float
        self.uniform_sky = uniform_sky

    @property
    def ratio2meters(self):
        return self.__normalise_factor  # type: float

    def enable_pol_filters(self, value):
        """

        :param value:
        :type value: bool
        :return:
        """
        self.__pol_filters = value

    def add_route(self, route):
        """
        Adds an ant-route in the world

        :param route: the new route
        :type route: Route
        :return: None
        """
        self.routes.append(route)

    def draw_top_view(self, width=None, length=None, height=None):
        """
        Draws a top view of the world and all the added paths in it.

        :param width: the width of the world
        :type width: int
        :param length: the length of the world
        :type length: int
        :param height: the height of the world
        :type height: int
        :return: an image of the top view
        """

        # set the default values to the dimensions of the world
        if width is None:
            width = self.width
        if length is None:
            length = self.length
        if height is None:
            height = self.height

        # create new image and drawer
        image = Image.new("RGB", (width, length), GROUND_COLOUR)
        draw = ImageDraw.Draw(image)

        # draw the polygons
        for p in self.polygons.scale(*((self.ratio2meters,) * 3)):
            pp = p * [width, length, height]
            draw.polygon(pp.xy, fill=pp.c_int32)

        # draw the routes
        nants = int(np.array([r.agent_no for r in self.routes]).max())      # the ants' ID
        nroutes = int(np.array([r.route_no for r in self.routes]).max())  # the routes' ID
        for route in self.routes:
            # transform the routes similarly to the polygons
            rt = route.scale(*(self.ratio2meters,) * 3)
            rt = rt * [width, length, height]
            h = np.linspace(0, 1, nants)[rt.agent_no-1]
            s = np.linspace(0, 1, nroutes)[rt.route_no-1]
            v = .5
            r, g, b = hsv_to_rgb(h, s, v)
            draw.line(rt.xy, fill=(int(r * 255), int(g * 255), int(b * 255)))

        return image, draw

    def draw_panoramic_view(self, x=None, y=None, z=None, r=0, width=None, length=None, height=None, update_sky=True):
        """
        Draws a panoramic view of the world

        :param x: The x coordinate of the agent in the world
        :type x: float
        :param y: The y coordinate of the agent in the world
        :type y: float
        :param z: The z coordinate of the agent in the world
        :type z: float
        :param r: The orientation of the agent in the world
        :type r: float
        :param width: the width of the world
        :type width: int
        :param length: the length of the world
        :type length: int
        :param height: the height of the world
        :type height: int
        :param update_sky: flag that specifies if we want to update the sky
        :type update_sky: bool
        :return: an image showing the 360 degrees view of the agent
        """

        # set the default values for the dimensions of the world
        if width is None:
            width = self.width
        if length is None:
            length = self.length
        if height is None:
            height = self.height
        if x is None:
            x = width / 2.
        if y is None:
            y = length / 2.
        if z is None:
            z = height / 2. + .06 * height

        # create ommatidia positions with respect to the resolution
        # (this is for the sky drawing on the panoramic images)
        thetas = np.linspace(-np.pi, np.pi, width, endpoint=False)
        phis = np.linspace(np.pi/2, 0, height / 2, endpoint=False)
        thetas, phis = np.meshgrid(phis, thetas)
        ommatidia = np.array([thetas.flatten(), phis.flatten()]).T

        image = Image.new("RGB", (width, height), GROUND_COLOUR)
        draw = ImageDraw.Draw(image)

        if self.uniform_sky:
            draw.rectangle((0, 0, width, height/2), fill=SKY_COLOUR)
        else:
            # create a compound eye model for the sky pixels
            self.eye = CompoundEye(ommatidia)
            self.eye.activate_pol_filters(self.__pol_filters)
            if update_sky:
                self.sky.obs.date = datetime.now()
                self.sky.generate()
            self.eye.facing_direction = -r
            self.eye.set_sky(self.sky)

            pix = image.load()
            for i, c in enumerate(self.eye.L):
                pix[i // (height / 2), i % (height / 2)] = tuple(np.int32(255 * c))

        R = np.array([
            [np.cos(r), -np.sin(r), 0],
            [np.sin(r), np.cos(r), 0],
            [0, 0, 1]
        ])
        thetas, phis, rhos = [], [], []
        pos = np.array([x, y, z]) / self.ratio2meters
        pos *= np.array([width, length, height])
        for p in self.polygons.scale(*((self.ratio2meters,) * 3)):
            pp = p * [width, length, height]
            theta, phi, rho = vec2sph((pp.xyz - pos).dot(R))
            thetas.append(theta)
            phis.append(phi)
            rhos.append(rho)

        thetas = height * ((np.array(thetas) % np.pi) / np.pi)
        phis = width * ((np.pi + np.array(phis)) % (2 * np.pi)) / (2 * np.pi)
        rhos = la.norm(np.array(rhos), axis=-1)
        ind = np.argsort(rhos)[::-1]
        for theta, phi, c in zip(thetas[ind], phis[ind], self.polygons.c_int32[ind]):
            if phi.max() - phi.min() < width/2:  # normal conditions
                p = tuple((b, a) for a, b in zip(theta, phi))
                draw.polygon(p, fill=tuple(c))
            else:   # in case that the object is on the edge of the screen
                phi0, phi1 = phi.copy(), phi.copy()
                phi0[phi < width/2] += width
                phi1[phi >= width/2] -= width
                p = tuple((b, a) for a, b in zip(theta, phi0))
                draw.polygon(p, fill=tuple(c))
                p = tuple((b, a) for a, b in zip(theta, phi1))
                draw.polygon(p, fill=tuple(c))

            # draw visible polygons

        return image, draw
