from .ask_buddy import AskBuddy
from .order_explorer import OrderExplorer

# Each entry becomes a tab in the app, in this order.
FEATURES = [
    OrderExplorer,
    AskBuddy,
]
