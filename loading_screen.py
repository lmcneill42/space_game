import pygame
from vector2d import Vec2d

class LoadingScreen(object):
    """ A loading screen to display while the resources are read in. It assumes
    direct control over the pygame display. The intention is you count your
    resources, construct the loading screen, and then just increment it after
    each resource is read. """

    def __init__(self, total, screen):
        """ Constructor. This actually does the initial draw. """
        self.total = total
        self.progress = 0
        self.screen = screen
        self.title = title = pygame.image.load("title.bmp")
        self.__draw()

    def increment(self):
        """ Increment the progress and refresh the screen. We also deal with
        events to keep the program responsive. """
        self.progress += 1
        for e in pygame.event.get():
            if e == pygame.QUIT:
                sys.exit(1)
        self.__draw()

    def __draw(self):
        """ Do the actual drawing and screen refresh. """

        # Clear the screen
        self.screen.fill((0, 0, 0))

        # Define the geometry of the loading bar.
        screen_rect = self.screen.get_rect()
        bar_rect = pygame.Rect((0, 0), (0, 0))
        bar_rect.width = screen_rect.width-60
        bar_rect.height = 60
        bar_rect.center = screen_rect.center
        bar_rect.top += self.title.get_height() / 2

        # Draw the title image above the loading bar.
        self.screen.blit(self.title,
                         Vec2d(bar_rect.center[0], bar_rect.top)
                         - Vec2d(self.title.get_width()/2, self.title.get_height()+10))

        # Draw the loading bar
        sz = 8
        pygame.draw.rect(self.screen, (255, 255, 255), bar_rect)
        bar_rect.inflate_ip(-sz, -sz)
        pygame.draw.rect(self.screen, (0, 0, 0), bar_rect)
        bar_rect.inflate_ip(-sz, -sz)
        left = bar_rect.left
        bar_rect.width = int(bar_rect.width * (float(self.progress)/self.total))
        bar_rect.left = left
        pygame.draw.rect(self.screen, (255, 255, 255), bar_rect)

        # Refresh the screen.
        pygame.display.update();
