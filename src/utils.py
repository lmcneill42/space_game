""" Basic building blocks of the game infrastructure. This includes a scheme
for assembly entitys from components, a system for loading entity
configuration from json data files, and other utilities. """

import random
import pygame
import sys
import os
import math
import collections
import yaml

from .loading_screen import LoadingScreen
from pymunk.vec2d import Vec2d

def fromwin(path):
    """Paths serialized on windows have \\ in them, so we need to convert
       them in order to read them on unix. Windows will happily read unix
       paths so we dont need to worry about going the other way."""
    return path.replace("\\", "/")

def bail():
    """ Bail out, ensuring the pygame windows goes away. """
    pygame.quit()
    sys.exit(1)

def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=collections.OrderedDict):
    """ Taken from http://stackoverflow.com/a/21912744

    We need to be able to iterate component keys in 'document order' because
    component types have implicit dependencies on other types, if we try to
    construct components in an arbitrary order then it might not work.

    A better solution to this problem would be to have component types declare
    their dependencies, and not allow them to access undeclared dependencies.

    For now, to get it working again, we will use this solution. """

    class OrderedLoader(Loader):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)

class GameInfo(object):
    """ Information about the running game. """
    def __init__(self):
        self.framerate = 0
        self.raw_framerate = 0
        self.max_framerate = 0
        self.min_framerate = 0
        self.time_ratio = 0
        self.framerates = []
    def update_framerate(self, framerate, raw_framerate, time_ratio):
        self.framerate = framerate
        self.min_framerate = min(self.min_framerate, framerate)
        self.max_framerate = max(self.max_framerate, framerate)
        self.raw_framerate = raw_framerate
        self.time_ratio = time_ratio
        self.framerates.append(framerate)
        if len(self.framerates) > 30:
            self.framerates.pop(0)

class GameServices(object):
    """ Functionality required of the game. """
    def __init__(self):
        pass
    def get_screen(self):
        """ Get the main drawing surface. """
        pass
    def get_player(self):
        """ Get the player's entity. """
        pass
    def get_camera(self):
        """ Get the camera. """
        pass
    def get_entity_manager(self):
        """ Get the entity manager. """
        pass
    def get_resource_loader(self):
        """ Get the object that can load images and so on. """
        pass
    def end_game(self):
        """ Tidy up and exit the program cleanly. """
        pass
    def get_info(self):
        """ Return information about the game. """
        return GameInfo()
    def lookup_type(self, class_path):
        """ Lookup a class by string name so that it can be dynamically
        instantiated. This is used for component and entity creation.
        This implementation has been pinched from an answer on stack overflow:
        http://stackoverflow.com/questions/16696225/dynamically-\
        instantiate-object-of-the-python-class-similar-to-php-new-classname"""

        try:
            module_path, class_name = class_path.rsplit(".", 1)
        except ValueError:
            print( "**************************************************************" )
            print( "ERROR CREATING OBJECT: '%s'" % class_path )
            print( "Must specify e.g. module.class in path. Got: '%s'." % class_path )
            print( "**************************************************************" )
            bail()           
            
        try:
            module = __import__(module_path, fromlist=[class_name])
        except ImportError:
            print( "**************************************************************" )
            print( "ERROR CREATING OBJECT: '%s'" % class_path )
            print( "The module '%s' could not be imported." % module_path )
            print( "**************************************************************" )
            bail()

        try:
            cls = getattr(module, class_name)
        except AttributeError:
            print( "**************************************************************" )
            print( "ERROR CREATING OBJECT: '%s'" % class_path )
            print( "The attribute '%s' could not be found." % class_name )
            print( "**************************************************************" )
            bail()

        # Might not actually be a class. But if it's a function that returns
        # an instance, who cares...
        return cls
    def get_debug_level():
        """ Get the debug level. """
        return 0

class Timer(object):
    """ A simple stopwatch - you tell it how much time has gone by and it
    tells you when it's done. """
    def __init__(self, period):
        self.timer = 0
        self.period = period
    def advance_to_fraction(self, frac):
        self.timer = self.period * frac
    def tick(self, dt):
        self.timer += dt
        return self.expired()
    def expired(self):
        return self.timer >= self.period
    def pick_index(self, num_indices):
        n = num_indices-1
        return min(int((self.timer/float(self.period))*n), n)
    def reset(self):
        self.timer -= self.period
    def randomise(self):
        self.timer = self.period * random.random()

class EntityManager(object):
    """ Manages a set of components systems which themselves manage components. """

    def __init__(self, game_services):
        """ Initialise the entity manager. """

        # Currently existing objects and queue of objects to create.
        self.objects = []
        self.new_objects = []
        self.new_parents = []

        # System stuff
        self.systems = {}
        self.systems_list = []

        # The services we require from the game. This is a little circular as it
        # exposes the entity manager but there you go...
        self.game_services = game_services

        # The componet class has a method manager_type() which defines what type of
        # system is supposed to manage components of that type. If we get a component
        # that claims to be managed by type t, we assume all components of that type
        # are managed by type t, and record the mapping here.
        #
        # Note that we could probably express this relationship a lot more cleanly. But
        # this will do for now...
        self.component_type_mapping = {}

    def create_queued_objects(self):
        """ Create objects that have been queued. """
        for o in self.new_objects:
            self.objects.append(o)
        for pair in self.new_parents:
            pair[0].add_child(pair[1])
        self.new_objects = []
        self.new_parents = []
        for s in self.systems_list:
            s.create_queued_components()

    def garbage_collect(self):
        """ Remove all of the objects that have been marked for deletion."""
        self.objects = [ x for x in self.objects if not x.is_garbage ]
        for s in self.systems_list:
            s.garbage_collect()

    def create_entity_with(self, *types, **kwargs):
        """ Create a new entity with a given list of components. """
        entity = self.create_entity()
        for t in types:
            component = t(entity, self.game_services, Config())
            component.setup(**kwargs)
            entity.add_component(component)
        return entity

    def create_entity(self, config_name=None, **kwargs):
        """ Add a new object. It is initialised, but not added to the game
        right away: that gets done at a certain point in the game loop."""

        loader = self.game_services.get_resource_loader()

        # load the config if specified.
        config = None
        if config_name is not None:
            if isinstance(config_name, Config):
                config = config_name
            else:
                config = loader.load_config_file(config_name)
        else:
            config = Config()

        # Instantiate the object.
        t = self.game_services.lookup_type(config.get_or_default("type", "src.utils.Entity"))
        obj = t(self.game_services)

        # Add components specified in the config.
        components = config.get_or_default("components", Config())
        for component in components:
            component_config = components[component]
            component_type = self.game_services.lookup_type(component)
            component = component_type(obj, self.game_services, component_config)
            component.setup(**kwargs)
            obj.add_component(component)

        # Add the object to the creation queue, and return it to the caller.
        self.new_objects.append(obj)

        # If the object needs to be added as a child, remember that.
        if "parent" in kwargs:
            self.new_parents.append((kwargs["parent"], obj))
        
        return obj
    
    def register_component_system(self, system):
        """ Register a component system. """
        system.setup(self.game_services)
        self.systems[system.__class__] = system
        self.systems_list.append(system) # Note: could just insert at right place.
        self.systems_list = sorted(
            self.systems_list,
            key = lambda x: x.priority
        )

    def get_component_system(self, component):
        """ Get the system that should manage a given component. """
        return self.get_component_system_by_type(component.manager_type())
        
    def get_component_system_by_type(self, t):
        """ Get the component system of the given type. """
        if not t in self.systems:
            self.register_component_system(t())
        return self.systems[t]

    def add_component(self, component):
        """ Add a component to the appropriate managing system. Note that the component
        knows what entity it is attached to. """

        # See comment above.
        if not component.__class__ in self.component_type_mapping:
            self.component_type_mapping[component.__class__] = component.manager_type()

        # Do the business.
        self.get_component_system(component).add_component(component)

    def get_system_by_component_type(self, component_type):
        """ Get the component system meant to manage a given component type. """
        # If we haven't seen a component of this concrete type then
        # there is by definition nothing to remove.
        # Note: A potentially better way could be to instantiate the type and
        # as it what type is supposed to manage it, since it is the component
        # type the knows what its system should be. That would be more correct
        # than this since it would work for base classes too. Of course it
        # sounds a bit convoluted. If/when this becomes a problem im sure we
        # could shuffle the code into a more elegant solution.
        if component_type in self.component_type_mapping:
            system_type = self.component_type_mapping[component_type]
            system = self.get_component_system_by_type(system_type)
            return system
        return None

    def remove_component_by_concrete_type(self, entity, component_type):
        """ Remove the component of the given ***concrete*** type from the entity. """
        system = self.get_system_by_component_type(component_type)
        if system is not None:
            system.remove_object_component(entity, component_type)

    def get_component_of_type(self, entity, t):
        """ Get the component of a particular type on a particular entity. """
        system = self.get_system_by_component_type(t)
        if system is not None:
            return system.get_component(entity, t)

    def get_all_components(self, entity):
        """ Get all components of an entity. """
        for system in self.systems_list:
            for component in system.get_all_entity_components(entity):
                yield component

    def update(self, dt):
        """ Update all of the systems in priority order. """
        for system in self.systems_list:
            system.update(dt)
        for s in self.systems_list:
            s.do_on_object_killed()
        self.garbage_collect()

class ComponentSystem(object):
    """ Manages a set of entity components. It knows how to update the
    components over time, how to get the components out for a particular object,
    and how to remove components when their objects are dead. """

    def __init__(self):
        """ Initialise. """
        self.components = []
        self.components_to_add = []
        self.priority = 0
        self.object_map = {}

    def setup(self, game_services):
        self.game_services = game_services

    def do_on_object_killed(self):
        """ Fire on_object_killed() for components about to go."""
        for c in self.components:
            if c.is_garbage():
                c.on_object_killed()

    def create_queued_components(self):
        """ Create the queued components. """
        for c in self.components_to_add:
            self.create_queued_component(c)
        self.components_to_add = []

    def create_queued_component(self, component):
        """ Add the queued component. This can perform any final initialisation. """
        self.components.append(component)

    def add_component(self, component):
        """ Add a component. Note that it won't be created straight away. It
        will be added to a queue, and created at the start of the next frame. """
        key = (component.entity, component.__class__)
        assert not key in self.object_map
        self.components_to_add.append(component)
        self.object_map[key] = component
        
    def remove_component(self, component):
        """ Remove a particular component. """
        self.components.remove(component)
        key = (component.entity, component.__class__)
        assert key in self.object_map
        del self.object_map[key]

    def get_component(self, entity, component_type):
        """ Get a single component of a particular type."""
        key = (entity, component_type)
        if key in self.object_map:
            return self.object_map[key]
        else:
            return None

    def get_all_entity_components(self, entity):
        """ Get all components associated with an entity. """
        for c in self.components:
            if c.entity == entity:
                yield c
    
    def remove_object_component(self, entity, component_type):
        """ Remove the component of a particular concrete type from an object. """
        component = self.get_component(entity, component_type)
        if component is not None:
            self.remove_component(component)

    def garbage_collect(self):
        """ Remove all dead components. """
        to_remove = [x for x in self.components if x.is_garbage()]
        for component in to_remove:
            self.remove_component(component)
            
    def update(self, dt):
        """ Update the components. """
        for component in self.components:
            component.update(dt)

# You will notice some overlap between entitys and components e.g.
# create_entity(), get_system_by_type(). I think eventually everything
# in Entity apart from is_garbage() i.e. config and game services will
# move completely into components. Currently all that derived entitys
# do is initialise() themselves with different components.

class Component(object):
    """ A entity component. """
    
    def __init__(self, entity, game_services, config):
        """ Initialise the component. """
        self.entity = entity
        self.game_services = game_services
        self.config = config

    def setup(self, **kwargs):
        """ Do any extra initialisation based on optional arguments. """
        pass
        
    def manager_type(self):
        """ Return the type of system that should be managing us. """
        return ComponentSystem
    
    def is_garbage(self):
        """ Is our entity dead? """
        return self.entity.is_garbage
    
    def update(self, dt):
        """ Update the component. """
        pass
    
    def on_object_killed(self):
        """ Do something when the object is killed. """
        pass

    def get_system_by_type(self, t):
        """ Get the system of type "t". Note that there should not be more than
        one system of a given type."""
        return self.entity.get_system_by_type(t)

    def create_entity(self, *args, **kwargs):
        """ Create a new entity with the given config and args. """
        return self.entity.create_entity(*args, **kwargs)

    def get_component(self, t):
        """ Return the component of a given type. Note that eventually this
        should be restricted such that a component has a formal list of
        dependencies, and it can only get at components of those types. As
        it stands anything can fiddle with anything.

        Note: this will crash if the object contains more than one component
        of this type. """
        return self.entity.get_component(t)

    def get_children_with_component(self, t):
        """ Get each (direct) child entity with a given component type. """
        return self.entity.get_children_with_component(t)

class Entity(object):
    """ An object in the game. It knows whether it needs to be deleted, and
    has access to object / component creation services. """

    def __init__(self, game_services):
        """ Constructor. Since you don't have access to the game services
        in __init__, more complicated initialisation must be done in
        initialise()."""
        self.is_garbage = False
        self.game_services = game_services
        self.children = []
        self.parent = None

    def kill(self):
        """ Mark the object for deletion. """
        # Note: I'm not sure whether objects being kill()ed twice should
        # count as a bug. I was getting exceptions in physics engine
        # callbacks due to this happening. Checking whether the object
        # is garbage before doing the business solves the problem - but
        # it could be I've just "fixed the symptom." I'm treating it as
        # not a bug, since kill() is a "public" API and I don't think it
        # makes sense to have the caller check is_garbage before calling it.
        if not self.is_garbage:

            # Set the garbage flag.
            self.is_garbage = True

            # Kill all of our children. Note that we copy the list because
            # killing a child removes it from the parent.
            children = self.children[:]
            for child in children:
                child.kill()

            # If we are a child, break the link with our parent.
            if self.parent is not None:
                self.parent.children.remove(self)
            self.parent = None

    def add_component(self, component):
        """ Shortcut to add a component. """
        self.game_services.get_entity_manager().add_component(component)

    def get_system_by_type(self, t):
        """ Get the system of type "t". Note that there should not be more than
        one system of a given type."""
        return self.game_services.get_entity_manager().get_component_system_by_type(t)

    def create_entity(self, *args, **kwargs):
        """ Create a new entity with the given config and args. """
        return self.game_services.get_entity_manager().create_entity(*args, **kwargs)

    def get_component(self, t):
        """ Return the components of a given type. Note that eventually this
        should be restricted such that a component has a formal list of
        dependencies, and it can only get at components of those types. As
        it stands anything can fiddle with anything.

        Note: this will crash if the object contains more than one component
        of this type. """
        return self.game_services.get_entity_manager().get_component_of_type(self, t)

    def get_children_with_component(self, t):
        """ Get each (direct) child entity with a given component type. """
        for entity in self.children:
            if entity.get_component(t) is not None:
                yield entity

    def get_children(self):
        """ Get all of the children. """
        for entity in self.children:
            yield entity

    def add_child(self, obj):
        """ Add a child entity. """
        assert obj.parent is None
        self.children.append(obj)
        obj.parent = self

    def is_descendant(self, obj):
        """ Is this object descended from that one? """
        return obj.is_ancestor(self)

    def is_ancestor(self, obj):
        """ Is that object descended from this one? """
        if obj == self:
            return True
        for c in self.children:
            if c.is_ancestor(obj):
                return True
        return False

class Config(object):
    """ A hierarchical data store. """

    def __init__(self, a_dict=None):
        """ Initialise an empty data store, or a wrapping one if a dictionary
        is provided."""

        # If this node is not a leaf, then this will contain the data
        # that defines the child nodes.
        self.__data = collections.OrderedDict()

        # If this node is a leaf, then this will contain its value.
        self.__value = None

        # If this tree was read from a file, this will be the filename.
        self.__filename = None

        # Name of the parent file.
        self.__parent_filename = None

        # If data specified, build a config.
        if a_dict is not None:
            self.__data = self.__build_config_dict(a_dict).__data

    def load(self, filename):
        """ Load data from a file. Remember the file so we can save it later.

        The filename here is relative to the game 'res' dir.

        If there is an error loading the file, noisily abort the program - it's
        probably a silly mistake that needs fixing. And config loading can
        happen inside physics callbacks, wherein exceptions get ignored for
        some reason!

        If the file contains a 'derive_from' key then load a parent config
        recursively until there is no more derivation. """

        self.load_from(os.path.join("res/configs", filename))

    def load_from(self, filename):
        """ Load data from a file. Remember the file so we can save it later.

        If there is an error loading the file, noisily abort the program - it's
        probably a silly mistake that needs fixing. And config loading can
        happen inside physics callbacks, wherein exceptions get ignored for
        some reason!

        If the file contains a 'derive_from' key then load a parent config
        recursively until there is no more derivation. """

        self.__filename = filename

        # Try to load the config from the file.
        print( "Loading config: ", self.__filename )
        data = collections.OrderedDict()
        try:
            data = ordered_load(open(self.__filename, "r"))
        except Exception as e:
            print( e )
            print( "**************************************************************" )
            print( "ERROR LOADING CONFIG FILE: ", self.__filename )
            print( "Probably either the file doesn't exist, or you forgot a comma!" )
            print( "**************************************************************" )
            bail() # Bail - we might be in the physics thread which ignores exceptions

        # Transform the data into a Config tree.
        self.__data = self.__build_config_dict(data).__data

    def save(self):
        """ Save to our remembered filename. """
        self.save_as(self.__filename)

    def save_as(self, filename):
        """ Save to given filename. """
        data = self.__config_to_dict()
        yaml.safe_dump(data, open(filename, "w"))

    def get_dict(self):
        """ Get the config as a dictionary. """
        return self.__config_to_dict()

    def __getitem__(self, key):
        """ Get some data out. """
        got = self.get_or_none(key)
        if got is None:
            print( "**************************************************************" )
            print( self.__data )
            print( "ERROR READING CONFIG ATTRIBUTE: %s" % key )
            print( "CONFIG FILE: %s" % self.__filename )
            print( "It's probably not been added to the file, or there is a bug." )
            print( "**************************************************************" )
            bail() # Bail - we might be in the physics thread which ignores exceptions
        return got

    def __iter__(self):
        """ Iterate the key-value pairs in the config. """
        if self.__data is not None:
            for key in self.__data:
                yield key
        
    def get_or_default(self, key, default):
        """ Get some data out. """
        ret = self.__get(key)
        if ret is not None:
            return ret
        else:
            return default

    def get_or_none(self, key):
        """ Get some data, or None if it isnt found. """
        return self.__get(key)

    def __get(self, key):
        """ Retrieve some data from our data store."""
        ret = self.__get_config(key)
        if ret is not None:
            if ret.__value is not None:
                return ret.__value
        return ret

    def __get_config(self, key):
        """ Retrieve some data from our data store."""
        if key in self.__data:
            return self.__data[key]
        else:
            return None

    def __build_config_dict(self, data):
        """ Build a config tree from a dictionary or leaf value. """

        # Use a temporary config.
        ret = Config()

        # Determine what sort of data we have
        is_dict = False
        try:
            for key in data:
                value = data[key]
                pass
            is_dict = True
        except:
            pass

        # Build config based on input type.
        if is_dict:

            # Build the tree.
            for key in data:
                value = data[key]
                ret.__data[key] = self.__build_config_dict(value)

            # If there is a parent config then load and merge it in.
            if "derive_from" in data:

                # Load the parent config
                ret.__parent_filename = data["derive_from"]
                parent = Config()
                parent.load(ret.__parent_filename)

                # Merge the config we just built with our parent.
                tmp = Config()
                tmp.__data = ret.__data
                parent.__merge_in(tmp)
                ret.__data = parent.__data
                
                # Remove the 'derive_from' entry as it has been dealt with.
                del ret.__data["derive_from"]
        else:
            ret.__value = data

        return ret

    def __merge_in(self, config):
        """ Overlay another config onto ourself. """
        if config.__value is not None:
            self.__value = config.__value
            return
        for key in config.__data:
            child = config.__data[key]
            self_child = self.__get_config(key)
            if self_child is not None:
                self_child.__merge_in(child)
            else:
                self.__data[key] = child

    def __config_to_dict(self):
        """ Turn the config tree into a plain dictionary. """
        if self.__value is not None:
            return self.__value
        ret = collections.OrderedDict()
        for key in self.__data:
            child = self.__data[key]
            ret[key] = child.__config_to_dict()
        return ret

class ResourceLoader(object):
    """ A resource loader - loads and caches resources which can be requested by the game. """
    
    def __init__(self):
        """ Initialise the resource loader. """
        self.images = {}
        self.animations = {}
        self.fonts = {}
        self.configs = {}
        self.sounds = {}
        self.minimise_image_loading = False

    def preload(self, screen):
        """ Preload certain resources to reduce game stutter. """

        # List all animation frames.
        anims = self.__list_animations()
        images = []
        for anim in anims:
            anim = self.__load_animation_definition(anim)
            images += anim["frames"]

        # List all config files.
        configs = self.__list_configs()

        # Number of steps.
        count = len(images) + len(configs)
        assert count > 0
        loading = LoadingScreen(count, screen)

        # Read in the frames.
        for filename in images:
            self.load_image(filename)
            loading.increment()

        # Read in the configs.
        for config in configs:
            self.load_config_file(config)
            loading.increment()

    def load_font(self, filename, size):
        """ Load a font from the file system. """
        if not (filename, size) in self.fonts:
            self.fonts[(filename, size)] = pygame.font.Font(filename, size)
        return self.fonts[(filename, size)]
        
    def load_image(self, filename):
        """ Load an image from the file system. """
        filename = fromwin(filename)
        if not filename in self.images:
            self.images[filename] = pygame.image.load(filename).convert_alpha()
            print( "Loaded image: %s" % filename )
        return self.images[filename]

    def __list_animations(self):
        """ List all of the available animations. """
        anims = []
        dirname = "res/anims"
        for anim_name in os.listdir(dirname):
            anim_file = os.path.join(dirname, os.path.join(anim_name, "anim.txt"))
            if os.path.isfile(anim_file):
                anims.append(anim_name)
        return anims

    def __list_configs(self, rel_dir=None):
        """ List all available configs. """
        configs = []
        dirname = "res/configs"
        if rel_dir is not None:
            dirname = os.path.join(dirname, rel_dir)

        for config_or_dir in os.listdir(dirname):

            # Get the name of the config or subdir relative to the configs
            # directory.
            rel_name = config_or_dir
            if rel_dir is not None:
                rel_name = os.path.join(rel_dir, rel_name)

            # Get the actual filename of the config / dir
            config_or_dir_path = os.path.join(dirname, config_or_dir)

            # If it's a config file, yield the relative name. Otherwise, walk
            # the directory.
            if os.path.isfile(config_or_dir_path):
                fname, ext = os.path.splitext(config_or_dir_path)
                if ext.lower() == ".txt":
                    configs.append(rel_name)
            elif os.path.isdir(config_or_dir_path):
                configs += self.__list_configs(rel_name)

        # Return the list we built.
        return configs

    def __load_animation_definition(self, name):
        """ Load the definition of an animation, included the names of all
        frames. """
        fname = os.path.join(os.path.join("res/anims", name), "anim.txt")
        anim = ordered_load(open(fname))
        anim["frames"] = []
        for i in range(anim["num_frames"]):
            # If we want to load faster disable loading too many anims...
            if self.minimise_image_loading and anim["num_frames"] > 10 and i % 10 != 0:
                continue
            padded = (4-len(str(i)))*"0" + str(i)
            img_name = anim["name_base"] + padded + anim["extension"]
            img_filename = os.path.join(os.path.dirname(fname), img_name)
            anim["frames"].append(img_filename)
        return anim

    def load_animation(self, filename):
        """ Load an animation from the filesystem. """
        if not filename in self.animations:
            anim = self.__load_animation_definition(filename)
            frames = [self.load_image(x) for x in anim["frames"]]
            self.animations[filename] = (frames, anim["period"])
            print( "Loaded animation: %s" % filename )
        (frames, period) = self.animations[filename]
        return Animation(frames, period)

    def load_config_file(self, filename):
        """ Read in a configuration file. """
        if not filename in self.configs:
            c = Config()
            c.load(filename)
            self.configs[filename] = c
        return self.configs[filename]

    def load_config_file_from(self, filename):
        """ Load a config from a path, not relative to the res dir. """
        c = Config()
        c.load_from(filename)
        return c

    def load_sound(self, filename):
        """ Load a sound. """
        if not filename in self.sounds:
            dirname = "res/sounds"
            self.sounds[filename] = Sound(os.path.join(dirname, filename))
        return self.sounds[filename]

class Sound(object):
    """ A sound that can be played. """

    def __init__(self, filename):
        """ Load the pygame sound. """
        self.__sound = pygame.mixer.Sound(filename)

    def play_positional(self, position_wrt_listener):
        """ Play at a volume related to the position. """

        # Just use linear attenuation.
        dist = position_wrt_listener.length
        max_dist = 750
        volume = min(max(1.0 - dist/max_dist, 0), 1)

        # Play at the attenuated volume.
        self.play(volume)

    def play(self, volume=1.0):
        """ Play at a fraction of the volume. """
        assert 0 <= volume and volume <= 1
        # Note: this is probably not quite correct, since if the sound
        # is already playing then set_volume() will set the volume on
        # it. I'm not sure if you can play the same sound multiple
        # times simultaneously. Might need to create copies of the
        # sound, I'm not sure.
        if volume > 0.05:
            self.__sound.set_volume(volume)
            self.__sound.play()

class Animation(object):
    """ A set of images with a timer which determines what image gets drawn
    at any given moment. """
    def __init__(self, frames, period):
        self.frames = frames
        self.timer = Timer(period)
    def tick(self, dt):
        return self.timer.tick(dt)
    def reset(self):
        self.timer.reset()
    def randomise(self):
        self.timer.randomise()
    def get_max_bounds(self):
        # Assume all frames the same size. Return biggest rect considering
        # all possible rotations.
        rect = self.frames[0].get_rect()
        size = math.sqrt(rect.width*rect.width + rect.height*rect.height)
        rect.width = size
        rect.height = size
        return rect
