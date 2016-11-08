#!/usr/bin/env python2

import src.game
import sys
import cProfile

def main():
    """ Run the game! """
    game = src.game.Game()
    game.run()

if __name__ == '__main__':

    # Braindead arg parsing.
    do_profile=False
    if len(sys.argv) > 1:
        do_profile = sys.argv[1] == "--profile"

    # Do profiling if we've asked for it.
    if do_profile:
        cProfile.run("main()", "profile_results")
    else:
        main()
