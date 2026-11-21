"""内置拓展领域。"""

from sr.plugin import Domain

from .lookup import Lookup
from .map import Map

DOMAIN = Domain(name="builtin", extenders=(Map, Lookup))
