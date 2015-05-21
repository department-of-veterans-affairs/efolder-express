from twisted.application.service import ServiceMaker


EFolderExpress = ServiceMaker(
    "The eFolder express application.",
    "efolder_express.tap",
    "Download an eFolder in a single click!",
    "efolder-express",
)
