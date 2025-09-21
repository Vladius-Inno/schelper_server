import fastui
from fastui import components as c
print([n for n in dir(c) if 'Form' in n or 'Input' in n or 'Field' in n or 'Button' in n])
print('components count:', len([n for n in dir(c) if n[0].isupper()]))
print([n for n in dir(c) if n[0].isupper()][:50])
