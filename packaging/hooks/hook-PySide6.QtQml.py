"""Collect the QML modules used by the app and its pinned FluentUI controls."""
from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()

def needed(entry):
    destination = entry[1].replace('\\', '/')
    relative = destination.split('/qml/', 1)[-1]
    if relative.startswith(('QtQuick/Scene2D', 'QtQuick/Scene3D', 'QtQuick/VirtualKeyboard')):
        return False
    return relative == 'QtQuick' or relative.startswith(('QtQuick/', 'QtQml', 'Qt5Compat/GraphicalEffects', 'Qt/labs/qmlmodels'))

binaries += [entry for entry in qml_binaries if needed(entry)]
datas += [entry for entry in qml_datas if needed(entry)]
