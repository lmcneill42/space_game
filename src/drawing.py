""" Everything that draws itself on the screen is a drawable. A drawable is
a special kind of component that knows how to draw itself given a surface
and a camera. """

import pygame
import os
import json

from vector2d import Vec2d

from utils import *

class Drawing(ComponentSystem):
    """ A class that manages a set of things that can draw themselves. """

    def draw(self, camera):
        """ Draw the drawables in order of layer. """
        self.components = sorted(self.components, lambda x, y: cmp(x.level, y.level))
        for drawable in self.components:
            drawable.draw(camera)

class Drawable(Component):
    """ Base class for something that can be drawn. """
    def __init__(self, game_object):
        Component.__init__(self, game_object)
        self.level = 0
    def manager_type(self):
        return Drawing
    def draw(self, camera):
        pass

class AnimBodyDrawable(Drawable):
    """ Draws an animation at the position of a body. """
    def __init__(self, obj, anim, body):
        Drawable.__init__(self, obj)
        self.anim = anim
        self.body = body
        self.kill_on_finished = False
    def update(self, dt):
        if self.anim.tick(dt):
            if self.kill_on_finished:
                self.game_object.kill()
            else:
                self.anim.reset()
    def draw(self, camera):
        self.anim.draw(self.body.position, camera)

class HealthBarDrawable(Drawable):
    """ Draws a health bar above a body. """
    def __init__(self, obj, body):
        Drawable.__init__(self, obj)
        self.body = body
    def draw(self, camera):
        rect = pygame.Rect(0, 0, self.body.size*2, 6)
        rect.center = camera.world_to_screen(self.body.position)
        rect.top = rect.top - (self.body.size + 10)
        pygame.draw.rect(camera.surface(), (255, 0, 0), rect)
        rect.width = int(self.game_object.hp/float(self.game_object.max_hp) * rect.width)
        pygame.draw.rect(camera.surface(), (0, 255, 0), rect)

class BulletDrawable(Drawable):
    """ A drawable that draws an image aligned with the relative velocity
    of a body to the player """
    def __init__(self, bullet, image, body, player_body):
        Drawable.__init__(self, bullet)
        self.image = image
        self.body = body
        self.player_body = player_body
    def draw(self, camera):
        screen = camera.surface()
        relative_velocity = self.body.velocity - self.player_body.velocity
        rotation = relative_velocity.get_angle()
        rotated = pygame.transform.rotate(self.image, 90 - rotation + 180)
        pos = camera.world_to_screen(self.body.position) - Vec2d(rotated.get_rect().center)
        screen.blit(rotated, pos)

class WinLoseDrawable(Drawable):
    """ A drawable for displaying the result of the game. """
    def __init__(self, camera, image):
        Drawable.__init__(self, camera)
        self.image = image
        self.level = 999
    def draw(self, camera):
        screen = camera.surface()
        pos = Vec2d(screen.get_rect().center) - Vec2d(self.image.get_size())/2
        screen.blit(self.image, (int(pos.x), int(pos.y)))

class BackgroundDrawable(Drawable):
    """ A drawable for a scrolling background. """
    def __init__(self, camera, image):
        Drawable.__init__(self, camera)
        self.image = image
        self.level = -999
    def draw(self, camera):
        screen = camera.surface()
        (image_width, image_height) = self.image.get_size()
        (screen_width, screen_height) = screen.get_size()
        pos = self.game_object.position
        x = int(pos.x)
        y = int(pos.y)
        start_i = -(x%image_width)
        start_j = -(y%image_width)
        for i in xrange(start_i, screen_width, image_width):
            for j in xrange(start_j, screen_height, image_height):
                screen.blit(self.image, (i, j))

class Polygon(object):
    """ A polygon. Used to be used for bullets. """
    @classmethod
    def make_bullet_polygon(a, b):
        perp = (a-b).perpendicular_normal() * (a-b).length * 0.1
        lerp = a + (b - a) * 0.1
        c = lerp + perp
        d = lerp - perp
        return Polygon((a,c,b,d,a))
    def __init__(self, points):
        self.points = [p for p in points]
        self.colour = (255, 255, 255)
    def draw(self, camera):
        transformed = [camera.world_to_screen(x) for x in self.points]
        pygame.draw.polygon(camera.surface(), self.colour, transformed)
