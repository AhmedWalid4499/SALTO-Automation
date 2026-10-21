from .ask_buddy import AskBuddy
from .hoto import HotoPrep
from .order_explorer import OrderExplorer
from .org_chart import OrgChartFinder

# Each entry becomes a tab in the app, in this order.
FEATURES = [
    OrderExplorer,
    HotoPrep,
    OrgChartFinder,
    AskBuddy,
]
