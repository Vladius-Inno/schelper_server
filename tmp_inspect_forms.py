import inspect
from fastui import components as c
print('ModelForm signature:', inspect.signature(c.ModelForm))
print(inspect.getsource(c.ModelForm))
print('Form signature:', inspect.signature(c.Form))
print(inspect.getsource(c.Form))
print('FormFieldInput signature:', inspect.signature(c.FormFieldInput))
