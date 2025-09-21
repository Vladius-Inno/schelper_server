import inspect
from fastui import components as c
print([n for n in dir(c) if 'Form' in n])
print(c.Form)
