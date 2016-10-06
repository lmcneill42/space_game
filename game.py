#!/bin/python2

import pygame
import math
import random
import os
import json
import sys

from vector2d import Vec2d

from physics import *
from drawing import *
from utils import *
from loading_screen import *
from input_handling import *
                
def main():
    game = Game()
    game.run()

class Game(object):
    
    def __init__(self):
        """ Initialise the game systems. """

        # The player
        self.player = None

        # The main camera.
        self.camera = None

        # The enemy.
        self.carrier = None

        # The physics system.
        self.physics = Physics()

        # The drawing system.
        self.drawing = Drawing()

        # The input handling system.
        self.input_handling = InputHandling()

        # Currently existing objects and queue of objects to create.
        self.objects = []
        self.new_objects = []

        # The configuration.
        self.config = Config()
        self.config.load("config.txt")

        # Configure the drawing.
        self.drawing.minimise_image_loading = self.config.get_or_default("minimise_image_loading", False)

    def get_camera(self):
        """ Get the camera. """
        return self.camera

    def get_player(self):
        """ Get the player. """
        return self.player

    def get_physics(self):
        """ Get the physics system. """
        return self.physics

    def get_drawing(self):
        """ Get the drawing system. """
        return self.drawing

    def get_input_handling(self):
        """ Get the input handling system. """
        return self.input_handling

    def garbage_collect(self):
        """ Remove all of the objects that have been marked for deletion."""
        self.objects = [ x for x in self.objects if not x.is_garbage ]

    def load_config_file(self, filename):
        """ Read in a configuration file. """
        c = Config()
        c.load(filename)
        return c

    def create_game_object(self, t, config):
        """ Add a new object. It is initialised, but not added to the game
        right away: that gets done at a certain point in the game loop."""
        config = load_config_file(config)
        obj = t()
        obj.initialise(self, config)
        self.new_objects.append(obj)
        return obj
    
    def run(self):
        """ The game loop. This performs initialisation including setting
        up pygame, and shows a loading screen while certain resources are
        preloaded. Then, we enter the game loop wherein we remain until the
        game is over. If the file "preload.txt" does not exist, then it will
        be filled with a list of resources to preload next time the game is
        run. """
        
        # Initialise
        pygame.init()
        screen = pygame.display.set_mode((self.config.get_or_default("screen_width", 1024), 
                                          self.config.get_or_default("screen_height", 768)))

        # Preload certain images.
        preload_name = "preload.txt"
        if self.drawing.minimise_image_loading:
            preload_name = "preload_min.txt"
        if os.path.isfile(preload_name):
            filenames = json.load(open(preload_name, "r"))
            loading = LoadingScreen(len(filenames), screen)
            for filename in filenames:
                self.drawing.load_image(filename)
                loading.increment()

        # Game state
        self.camera = Camera(screen)
        self.add_new_object(self.camera)
        
        self.player = Player(self.camera)
        self.add_new_object(self.player)
        
        self.drawing.add_drawable(BackgroundDrawable(self.camera, self.drawing.load_image("res/images/star--background-seamless-repeating9.jpg")))

        self.carrier = Carrier()
        self.add_new_object(self.carrier)
        self.carrier.body.position = Vec2d((0, 100))

        self.physics.add_collision_handler(BulletShooterCollisionHandler())

        # Main loop.
        running = True
        fps = 60
        clock = pygame.time.Clock()
        while running:

            ## Create any queued objects
            for o in self.new_objects:
                self.objects.append(o)
                self.new_objects = []

            # Input
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif self.input_handling.handle_input(e):
                    pass

            tick = 1.0/fps # Use idealised tick time.

            # Update
            for o in self.objects:
                o.update(tick) 

            # Collision detection.
            self.physics.update(tick)

            # Update the drawables.
            self.drawing.update(tick)

            # Destroy anything that is now dead.
            self.garbage_collect()

            # Draw
            screen.fill((0, 0, 0))
            self.drawing.draw(self.camera)
            pygame.display.update()

            # Maintaim frame rate.
            clock.tick(fps)

        # Finalise
        pygame.quit()

        # Save a list of images to preload next time.
        if not os.path.isfile(preload_name):
            json.dump(
                self.drawing.images.keys(),
                open(preload_name, "w"),
                indent=4,
                separators=(',', ': ')
            )

class Config(object):
    """ A hierarchical data store. """
    
    def __init__(self):
        """ Initialise an empty data store. """
        self.parent = None
        self.data = {}
        self.filename = None
        
    def load(self, filename):
        """ Load data from a file. Remember the file so we can save it later. """
        self.filename = filename
        if (os.path.isfile(self.filename)):
            self.data = json.load(open(self.filename, "r"))
        parent_filename = self.__get("derive")
        if parent_filename is not None:
            self.parent = Config()
            self.parent.load(self.parent_filename)
            
    def save(self):
        """ Save to our remembered filename. """
        json.dump(self.data, open(self.filename, "w"), indent=4, separators=(',', ': '))

    def __getitem__(self, key):
        """ Get some data out. """
        got = __get(key)
        if got is None:
            return self.parent[key]
        else:
            return got
        
    def get_or_default(self, key, default):
        """ Get some data out. """
        got = self[key]
        if got is None:
            return default
        else:
            return got

    def __get(self, key):
        """ Retrieve some data from our data store."""
        try:
            tokens = key.split(".")
            ret = self.data
            for tok in tokens:
                ret = ret[tok]
            return ret
        except:
            return None

class GameObject(object):
    """ An object in the game. It knows whether it needs to be deleted, and
    has access to object / component creation services. """

    def __init__(self):
        """ Constructor. Since you don't have access to the game services
        in __init__, more complicated initialisation must be done in
        initialise()."""
        self.is_garbage = False
        self.game_services = None

    def initialise(self, game_services, config):
        """ Initialise the object: create drawables, physics bodies, etc. """
        self.game_services = game_services
        self.config = config

    def update(self, dt):
        """ Perform a logical update: AI behaviours, game logic, etc. Note
        that physics simulation is done by adding a Body. """
        pass

    def kill(self):
        """ Mark the object for deletion and perform whatever game logic
        needs to be done when the object is destroyed e.g. spawn an
        explosion. """
        self.is_garbage = True

class Explosion(GameObject):
    """ An explosion. It will play an animation and then disappear. """

    def initialise(self, game_services, config):
        """ Create a body and a drawable for the explosion. """
        GameObject.initialise(self, game_services, config)
        anim = game_services.get_drawing().load_animation(config["anim_name"])
        self.body = Body(self)
        self.body.collideable = False
        self.drawable = AnimBodyDrawable(self, anim, self.body)
        self.drawable.kill_on_finished = True
        game_services.get_physics().add_body(self.body)
        game_services.get_drawing().add_drawable(self.drawable)

class Bullet(GameObject):

    def __init__(self):
        """ Initialise the bullet with its image and explosion name. """
        GameObject.__init__(self)

    def initialise(self, game_services, config):
        """ Build a body and drawable. The bullet will be destroyed after
        a few seconds. """
        GameObject.initialise(self, game_services, config)
        self.body = Body(self)
        self.body.size = config["size"]
        self.lifetime = Timer(config["lifetime"])
        img = self.game_services.get_drawing().load_image(config["image_name"])
        player_body = game_services.get_player().body
        drawable = BulletDrawable(self, img, self.body, player_body)
        game_services.get_physics().add_body(self.body)
        game_services.get_drawing().add_drawable(drawable)

    def update(self, dt):
        """ Advance the life timer. """
        GameObject.update(self, dt)
        if self.lifetime.tick(dt):
            self.kill()

    def kill(self):
        """ Spawn an explosion when the bullet dies. """
        GameObject.kill(self)
        explosion = self.game_services.create_game_object(Explosion, self.config["explosion_config"])
        explosion.body.position = Vec2d(self.body.position)

    def apply_damage(self, to):
        """ Apply damage to an object we've hit. """
        if self.config.get_or_default("destroy_on_hit", True):
            self.kill()
        to.receive_damage(self.config["damage"])

class ShootingBullet(Bullet):
    """ A bullet that is a gun! """

    def initialise(self, game_services, config):
        """ Initialise the shooting bullet. """
        Bullet.initialise(self, game_services, config)
        self.gun = Gun(self.body, game_services, game_services.load_config(config["gun_config"]))
        self.gunner = BurstFireGunnery(self.gun, config)
        
    def update(self, dt):
        """ Update the shooting bullet. """
        Bullet.update(self, dt)
        if not self.gunner.tracking:
            closest = self.game_services.get_physics().closest_body_of_type(
                self.body.position,
                self.config["track_type"]
            )
            if closest:
                self.gunner.track(closest)
        self.gun.update(dt)
        self.gunner.update(dt)

class Gun(object):
    """ Something that knows how to spray bullets. Note that this is not a
    game object, it's something game objects can use to share code. """

    def __init__(self, body, game_services, config):
        """ Inject dependencies and set up default parameters. """
        self.body = body
        self.game_services = game_services
        self.config = config
        self.shooting = False
        self.shooting_at = Vec2d(0, 0)
        self.shooting_at_screen = False
        self.shot_timer = 0

    def start_shooting_world(self, at):
        """ Start shooting at a point in world space. """
        self.shooting = True
        self.shooting_at = at
        self.shooting_at_screen = False

    def start_shooting_screen(self, at):
        """ Start shooting at a point in screen space. """
        self.start_shooting_world(at)
        self.shooting_at_screen = True

    def shooting_at_world(self):
        """ Get the point, in world space, that we are shooting at. """
        if self.shooting_at_screen:
            return self.game_services.get_camera().screen_to_world(self.shooting_at)
        else:
            return self.shooting_at

    def stop_shooting(self):
        """ Stop spraying bullets. """
        self.shooting = False

    def update(self, dt):
        """ Create bullets if shooting. Our rate of fire is governed by a timer. """
        if self.shot_timer > 0:
            self.shot_timer -= dt
        if self.shooting:
            shooting_at_world = self.shooting_at_world()
            shooting_at_dir = (shooting_at_world - self.body.position).normalized()
            while self.shot_timer <= 0:
                self.shot_timer += 1.0/self.config["shots_per_second"]
                bullet = self.game_services.create_game_object(self.config["bullet_type"],
                                                               self.game_services.load_config(self.config["bullet_config"]))
                muzzle_velocity = shooting_at_dir * self.config["bullet_speed"]
                muzzle_velocity.rotate(random.random() * self.config["spread"] - self.config["spread"]/2)
                bullet.body.velocity = self.body.velocity + muzzle_velocity
                bullet.body.position = Vec2d(self.body.position) + shooting_at_dir * (self.body.size+bullet.body.size+1)

class Shooter(GameObject):
    """ An object with a health bar that can shoot bullets. """

    def initialise(self, game_services, config):
        """ Create a body and some drawables. We also set up the gun. """
        GameObject.initialise(self, game_services, config)
        anim = game_services.get_drawing().load_animation(config["anim_name"])
        anim.randomise()
        self.hp = self.config["hp"]
        self.max_hp = self.config["max_hp"] # Rendundant, but code uses this.
        self.body = Body(self)
        self.body.mass = config["mass"]
        self.drawable = AnimBodyDrawable(self, anim, self.body)
        self.hp_drawable = HealthBarDrawable(self, self.body)
        game_services.get_physics().add_body(self.body)
        game_services.get_drawing().add_drawable(self.drawable)
        game_services.get_drawing().add_drawable(self.hp_drawable)
        self.gun = Gun(self.body, game_services, config)
        self.guns = [self.gun]

    def update(self, dt):
        """ Overidden to update the gun. """
        GameObject.update(self, dt)
        for g in self.guns:
            g.update(dt)

    def kill(self):
        """ Spawn an explosion on death. """
        GameObject.kill(self)
        explosion = self.game_services.create_game_object(Explosion, self.config["explosion_config"])
        explosion.body.position = Vec2d(self.body.position)

    def receive_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.kill()

class BurstFireGunnery(object):
    """ Shoots at something in bursts. """
    def __init__(self, gun, config):
        self.config = config
        self.gun = gun
        self.fire_timer = Timer(config["fire_period"])
        self.fire_timer.advance_to_fraction(0.8)
        self.burst_timer = Timer(config["burst_period"])
        self.tracking = None
    def track(self, body):
        self.tracking = body
    def update(self, dt):
        if self.tracking:
            if self.tracking.is_garbage():
                self.tracking = None
        if self.tracking:
            if not self.gun.shooting:
                if self.fire_timer.tick(dt):
                    self.fire_timer.reset()
                    self.gun.start_shooting_world(self.tracking.position)
            else:
                if self.burst_timer.tick(dt):
                    self.burst_timer.reset()
                    self.gun.stop_shooting()
                else:
                    # Maintain aim.
                    self.gun.start_shooting_world(self.tracking.position)
                    

class Target(Shooter):
    """ An enemy than can fly around shooting bullets. """

    def initialise(self, game_services, config):
        """ Overidden to configure the body and the gun. """
        Shooter.initialise(self, game_services, config)
        self.gunner = BurstFireGunnery(self.gun)

    def towards_player(self):
        """ Get the direction towards the player. """
        player = self.game_services.get_player()
        player_pos = player.body.position
        displacement = player_pos - self.body.position
        direction = displacement.normalized()
        return direction
                
    def update(self, dt):
        """ Logical update: shoot in bursts, fly towards the player and spawn
        more enemies. """

        # Call base class.
        Shooter.update(self, dt)

        # Accelerate towards the player.
        # Todo: make it accelerate faster if moving away from the player.
        player = self.game_services.get_player()
        player_pos = player.body.position
        displacement = player_pos - self.body.position
        direction = displacement.normalized()
        if displacement.length > self.config["desired_distance_to_player"]:
            acceleration = direction * self.config["acceleration"]
            self.body.velocity += acceleration * dt
        else:
            self.body.velocity += (player.body.velocity - self.body.velocity)*dt

        # Shoot!
        self.gunner.track(player.body)
        self.gunner.update(dt)

class Carrier(Target):
    """ A large craft that launches fighters. """

    def initialise(self, game_services, config):
        """ Overidden to configure the body and the gun. """
        Target.initialise(self, game_services, config)
        self.spawn_timer = Timer(config["spawn_period"])
        self.spawn_timer.advance_to_fraction(0.8)
    
    def update(self, dt):
        """ Overidden to launch fighters. """
        Target.update(self, dt)
        
        # Launch fighters!
        if self.spawn_timer.tick(dt):
            self.spawn_timer.reset()
            self.spawn()
            
    def spawn(self):
        """ Spawn more enemies! """
        for i in xrange(20):
            direction = self.towards_player()
            spread = self.config["takeoff_spread"]
            direction.rotate(spread*random.random()-spread/2.0)
            child = self.game_services.create_game_object(Target, self.game_services.load_config("fighter.txt"))
            child.body.velocity = self.body.velocity + direction * self.config["takeoff_speed"]
            child.body.position = Vec2d(self.body.position)

class Camera(GameObject):
    """ A camera, which drawing is done in relation to. """

    def __init__(self, screen):
        """ Initialise the camera. """
        GameObject.__init__(self)
        self.position = Vec2d(0, 0)
        self.target_position = self.position
        self.screen = screen

    def surface(self):
        """ Get the surface drawing will be done on. """
        return self.screen

    def update(self, dt):
        """ Update the camera. """
        self.position = self.target_position

    def world_to_screen(self, world):
        """ Convert from world coordinates to screen coordinates. """
        centre = Vec2d(self.screen.get_size())/2
        return centre + world - self.position

    def screen_to_world(self, screen):
        """ Convert from screen coordinates to world coordinates. """
        centre = Vec2d(self.screen.get_size())/2
        return screen + self.position - centre

class Player(Shooter):
    """ The player! """

    def initialise(self, game_services, config):
        """ Initialise with the game services: create an input handler so
        the player can drive us around. """
        Shooter.initialise(self, game_services, config)
        game_services.get_input_handling().add_input_handler(PlayerInputHandler(self))
        self.normal_gun = Gun(self.body,
                              game_services,
                              game_services.load_config(config["gun_config"]);
        self.torpedo_gun = ShootingBulletGun(self.body,
                                             game_services,
                                             game_services.load_config(config["torpedo_gun_config"]))
        self.guns = [self.normal_gun, self.torpedo_gun]
        self.gun = self.normal_gun

    def update(self, dt):
        """ Logical update: ajust velocity based on player input. """
        Shooter.update(self, dt)
        self.body.velocity -= (self.body.velocity * dt * 0.8)
        self.body.velocity += self.dir.normalized() * dt * 500 
        self.game_services.get_camera().target_position = Vec2d(self.body.position)

    def start_shooting(self, pos):
        for g in self.guns:
            g.start_shooting_screen(pos)

    def stop_shooting(self):
        for g in self.guns:
            g.stop_shooting()

    def is_shooting(self):
        return self.gun.is_shooting

class BulletShooterCollisionHandler(CollisionHandler):
    """ Collision handler to apply bullet damage. """
    def __init__(self):
        CollisionHandler.__init__(self, Bullet, Shooter)
    def handle_matching_collision(self, bullet, shooter):
        bullet.apply_damage(shooter)

if __name__ == '__main__':
    main()
