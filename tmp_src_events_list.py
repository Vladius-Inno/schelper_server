import inspect
import fastui
from fastui import events
print([n for n in dir(events) if n.lower().endswith('event')])
