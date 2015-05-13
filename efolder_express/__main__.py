import sys

from twisted.internet.task import react

from efolder_express.app import main


react(main, sys.argv[1:])
