import inspect, fastui, os
print('fastui file:', fastui.__file__)
try:
    from fastui._prebuilt import prebuilt_html
    print('prebuilt from _prebuilt')
except Exception as e:
    print('no _prebuilt import', e)
    prebuilt_html = fastui.prebuilt_html
print('signature:', inspect.signature(prebuilt_html))
print('source:')
print(inspect.getsource(prebuilt_html))
