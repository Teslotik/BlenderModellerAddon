'''
TODO
- заменить label `modifier.` на `nextmd.`
- составить пресет-перечень проверок в poll и поменять проверки
- составить приоритет свойств
- попробовать переместить tag_redraw в конец оператора, чтобы панель не проглючивала при запуске оператора
- проверка типов
- работа с множеством объектов
- перенести переменных часть в Property
- логику перекинуть в execute
- заменить update() на execute()
- хранить данные в одном массиве и не в нескольких и потом zip'овать их
- режим редактирования последнего добавленного модификатора
- сброс объектов до начального состояния в modal
- с зажатым Shift используется последний модификатор выбранного типа, а несоздаётся новый
- с зажатым Alt автоматически определяется последний модификатор
- return self
- вылетает после применения модального оператора если изменить свойство
- порядок property
- setup должжен вызывать apply() один раз в конце функции
- сбрасывать некоторые параметры при вызове модифкатора (чтобы их значения не оставались одинаковыми от вызова-к-вызову)
- draw
- единое отображение констант enum'ов
- проверить сброс флага existed
- назвать property также как они назыаются в модификаторах
- пересмотреть горячие клавиши, задействовать wasd
- поубирать и подобавлять execute'ы (в т.ч. в MOUSEMOVE)
- bl_context
- размер шрифта из стилей (в т.ч. внутри операторов где дёргаются методы text и sep)
- названия модификаторов в scroll modifiers
- применение модификаторов в move modifiers
- объединить scroll, move, sort modifiers
- orient objects копируют масштаб (не должно)


Инструменты/модификаторы
- показать/скрыть сетку по верх объекта / только сетка
- инструменты курсора
- sharing параметры через pastebin
- декали (граффити), маски
- сохранить и восстановить трансформацию
- удаление модификаторов

Правила именования
- bl_label = name + type        # Linear Array Modifier
- каждое новое слово пишется с большй буквы

'''

import os
import sys
from copy import copy
from math import degrees, radians
from types import LambdaType
from typing import Any, Dict, List

import blf
import bmesh
import bpy
import bpy.utils
from bmesh.types import BMEdge, BMVert
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
from bpy.types import (BevelModifier, Context, CurveModifier, DisplaceModifier,
                       EdgeSplitModifier, Event, Menu, Modifier, Object,
                       Operator, ScrewModifier, SimpleDeformModifier,
                       SpaceView3D, SubsurfModifier)
from bpy_extras.view3d_utils import region_2d_to_vector_3d
from mathutils import Euler, Matrix, Vector
import itertools
from math import isclose
# print(os.path.(__file__))
# # sys.path.append(os.path.dirname(__file__))




# from nmath.geometry import find_loop


'''
Shift+Mouse - сдвиг
Ctrl+Scroll - количество
Alt+Mouse - режим
X/Y/Z - ось
M - merge
C - clip
R - relative/local
'''


to_camel_case = lambda name: ''.join(i.capitalize() for i in type.split('_'))

def eyedropper(context:Context, x:float, y:float, exclude=None):
    viewport = context.space_data.region_3d.view_matrix.inverted()
    success, location, normal, face_index, obj, matrix = context.scene.ray_cast(
        context.evaluated_depsgraph_get(),
        viewport.translation,
        region_2d_to_vector_3d(context.region, context.region_data, (x, y))
    )
    if isinstance(exclude, (list, tuple)):
        if obj in exclude: return
    else:
        if obj is exclude: return
    return obj

def sort_modifiers(context:Context):
    pass

def find_loop(edge:BMEdge, a:BMVert, b:BMVert, angle:float, limit=radians(95)):
    loop = [edge, ]
    while True:
        if any((e.other_vert(b).co - b.co).angle(a.co - b.co) < limit for e in b.link_edges if e is not edge and e.is_contiguous and e.calc_length() > 10e-6): break
        neighbors = [e for e in b.link_edges if e is not edge and e.is_contiguous and e.calc_length() > 10e-6 and (e.other_vert(b).co - b.co).angle(a.co - b.co) > angle]
        if not neighbors: break
        # Ищем наиболее сонаправленное ребро относительно предыдущего
        edge = min(neighbors, key = lambda e: (e.other_vert(b).co - b.co).angle(a.co - b.co))
        if edge in loop: break
        loop.append(edge)
        b = edge.other_vert(a := b)
    return loop

def detect(angle:float, union:float, limit:float):
    mesh = bpy.context.active_object.data
    bm = bmesh.from_edit_mesh(mesh)

    edges = set(e for e in bm.edges if e.is_boundary or len(e.link_faces) == 2 and e.calc_face_angle() > angle)
    visited = set()
    for edge in edges:
        if edge in visited: continue
        edge.select_set(True)
        a, b = edge.verts
        if edge.calc_length() > 10e-6:
            visited.update(find_loop(edge, a, b, union, limit))
            visited.update(find_loop(edge, b, a, union, limit))
    # [e.select_set(True) for e in visited]
    indexes = [e.index for e in visited]

    bm.free()
    return indexes

def loop_select(angle:float):
    mesh = bpy.context.active_object.data
    bm = bmesh.from_edit_mesh(mesh)

    edges = set(e for e in bm.edges if e.select)
    for edge in edges:
        edge.select_set(True)
        a, b = edge.verts
        if edge.calc_length() > 10e-6:
            [e.select_set(True) for e in find_loop(edge, a, b, angle)]
            [e.select_set(True) for e in find_loop(edge, b, a, angle)]

    bm.free()

# detect(radians(85), radians(145))
# loop_select(radians(145))


# adjust = AdjustPane(Style.font_id)
# adjust.begin()
# adjust.text("Welcome back, ", newline = False)
# adjust.text("commander!")
# adjust.end()
# adjust.x = 50
# adjust.y = 150


def get_objects(context:Context, *filters):
    selected = context.selected_objects
    active = context.active_object
    objects = selected if active in selected else [active, ] + selected
    if not filters: return
    if len(filters) == 1:
        return [o for o in objects if filters[0](o)]
    return [[o for o in objects if key(o)] for key in filters]

def bubble_modifier(obj:Object, modifier:Modifier, reverse=True):
    if reverse:
        while obj.modifiers[-1] != modifier:
            bpy.ops.object.modifier_move_down(modifier = modifier.name)
        return
    while obj.modifiers[0] != modifier:
        bpy.ops.object.modifier_move_up(modifier = modifier.name)


class Style:
    active = None

    def __init__(self, Int, Float, true, false, none, String, axis, modify, title, text, hotkey, spacing, size, offset, font):
        self.Int = Int
        self.Float = Float
        self.true = true
        self.false = false
        self.none = none
        self.String = String
        self.axis = axis
        self.modify = modify
        self.title = title
        self.text = text
        self.hotkey = hotkey
        self.spacing = spacing
        self.size = size
        self.offset = offset
        self.font = font

gruvbox = Style(
    Int =    (0.721, 0.733, 0.149, 1.0),   # green
    Float =  (0.721, 0.733, 0.149, 1.0),   # green
    true =   (0.721, 0.733, 0.149, 1.0),   # green
    false =  (0.984, 0.286, 0.203, 1.0),   # red
    none =   (0.984, 0.286, 0.203, 1.0),   # red
    String = (0.721, 0.733, 0.149, 1.0),   # green
    axis =   (0.721, 0.733, 0.149, 1.0),   # green
    modify = (0.827, 0.525, 0.607, 1.0),   # purple
    title =  (0.843, 0.600, 0.129, 1.0),   # yellow
    text =   (0.835, 0.768, 0.631, 1.0),   # fg2
    hotkey = (0.572, 0.513, 0.454, 1.0),   # gray
    spacing = 4,
    size = 14,
    offset = 20,
    font = 0
)

Style.active = gruvbox

'''
pane = AdjustPane()
pane.title('Array')
pane.sep()
pane.prop('count', 'Scroll', lambda: modifier.count)

# self.draw = pane.draw

def draw(self, context):
    self.pane.draw(context)
'''
class AdjustPane:
    class Command:
        def __init__(self, draw=None, call=None, cancel=None):
            self.draw = draw
            self.call = call
            self.cancel = cancel
    
    class Observer:
        def __init__(self, value:LambdaType|Any, on_change):
            self.value = value
            self.cache = None
            self.on_change = on_change
        def update(self):
            value = self.value() if isinstance(self.value, LambdaType) else self.value
            if self.cache is not None and value != self.cache:
                self.on_change(value)
            self.cache = value
            return self

    def __init__(self, style):
        self.commands = []
        self.style = style
        self.handler = None
        self.draw = None
        self.drawing = False
        # Transformations
        self.cursor = Vector()
        self.offset = Vector((15, 5, 0))
        self.x = 0
        self.y = 0
        self.z = 0
        self.observers = {} # {name: observer}
        self.modified = None

    def remove(self):
        if self.handler: self.handler = SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
        return self

    def begin(self, x = 0.0, y = 0.0, z = 0.0):
        if self.drawing: self.end()
        self.drawing = True
        self.x = x
        self.y = y
        self.z = z
        if self.handler: self.handler = SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
        self.commands = []
        return self
    
    def end(self):
        self.drawing = False
        def call(self, context:Context):
            for cmd in self.commands:
                if cmd.call: cmd.call(self, context)
        def draw(this, context:Context):
            self.cursor.x = 0
            self.cursor.y = 0
            self.cursor.z = 0
            for observer in self.observers.values():
                observer.update()
            for cmd in self.commands:
                if cmd.draw: cmd.draw(self, context)
        self.draw = draw
        self.handler = SpaceView3D.draw_handler_add(draw, (None, None), 'WINDOW', 'POST_PIXEL')
        return call

    # ----------------------------------- Base components -----------------------------------

    def text(self, text, color=(1, 1, 1, 1), size=14, newline=True):
        def draw(this, context:Context):
            blf.position(self.style.font,
                self.x + self.cursor.x + self.offset.x,
                self.y + self.cursor.y + self.offset.y,
                self.z + self.cursor.z + self.offset.z
            )
            blf.size(self.style.font, size)
            blf.color(self.style.font,
                *(color() if isinstance(color, LambdaType) else color)
            )
            string = str(text() if isinstance(text, LambdaType) else text)
            blf.draw(self.style.font, string)
            w, h = blf.dimensions(self.style.font, string)
            if newline:
                self.cursor.y -= h + self.style.spacing
                self.cursor.x = 0
            else:
                self.cursor.x += w
        self.commands.append(
            self.Command(
                draw = draw
            )
        )
        return self

    def transform(self, x=None, y=None):
        def draw(this, context:Context):
            if x: self.cursor.x = x
            if y: self.cursor.y = -y
        self.commands.append(self.Command(
            draw = draw
        ))
        return self
    
    def move(self, dx=0.0, dy=0.0):
        def draw(this, context:Context):
            self.cursor.x += dx() if isinstance(dx, LambdaType) else dx
            self.cursor.y -= dy() if isinstance(dy, LambdaType) else dy
        self.commands.append(self.Command(
            draw = draw
        ))
        return self

    def sep(self, length:float, color=(1, 1, 1, 1)):
        blf.size(self.style.font, self.style.size)
        self.text('-' * length, color)
        return self

    def flush(self):
        self.modified = None

    # ----------------------------------- Composable -----------------------------------

    def header(self, text:str):
        self.move(dx = -self.style.offset)
        self.text(
            lambda: f'# {text}' if self.modified is None else self.modified,
            lambda: self.style.title if self.modified is None else self.style.modify,
            size = 30
        )
        return self

    def prop(self, text, key, value, subtype=None):
        self.transform(x = 50)
        blf.size(self.style.font, self.style.size)
        w, h = blf.dimensions(self.style.font, text)
        self.move(dx = -w)
        self.text(text, self.style.text, newline = False)
        self.move(dx = 10)
        kind = value()
        v = value
        if isinstance(kind, bool) or subtype is bool:
            v = lambda: ('ON' if value() else 'OFF')
            c = lambda: (self.style.true if value() else self.style.false)
        elif isinstance(kind, int) or subtype is int:
            c = self.style.Int
        elif isinstance(kind, float) or subtype is float:
            v = lambda: round(value(), 2)
            c = self.style.Float
        elif kind in ('X', 'Y', 'Z', '-X', '-Y', '-Z') or subtype == 'AXIS':
            c = self.style.axis
        elif isinstance(kind, str) or subtype is str:
            c = self.style.String
        else:
            c = lambda: self.style.none if value() is None else self.style.String
        self.text(v, c, newline = False)

        def observer(value):
            if type(value) is str: return
            if type(value) is bool: return
            self.modified = f'{text}: {value}'
        self.observers.update({
            text: self.Observer(v, on_change = observer)
        })

        self.transform(x = 180)
        self.text(key, self.style.hotkey)
        return self
    
    def status(self, text, enable:LambdaType, selected=lambda: False):
        self.transform(x = 50)
        blf.size(self.style.font, self.style.size)
        self.move(dx = lambda: -blf.dimensions(self.style.font, (text() if isinstance(text, LambdaType) else text))[0])
        # TODO Replace `hotkey` color with another or rename `hotkey`
        self.text(text, lambda: self.style.String if selected() else self.style.hotkey, newline = False)
        self.move(dx = 10)
        self.text(
            lambda: ('ON' if enable() else 'OFF'),
            lambda: (self.style.true if enable() else self.style.false),
        )

        return self

# TODO Test
# TODO добавление модификатора в правильном поряке (reversed)
# TODO настройка модификатора
# TODO создание снапшота
# TODO отметка был ли создан модификатор или использовался существующий
# NOTE можно не возвращать данные анализа, а хранить внутри этого класса
class ModifiersManager:
    class Command:
        def __init__(self, name:str, type:str, start:str, order:bool, setup:LambdaType, apply:LambdaType):
            self.name = name
            self.type = type
            self.start = start
            self.order = order
            self.setup = setup
            self.apply = apply
        def __eq__(self, modifier:Modifier):
            if modifier.type != self.type: return False
            if not modifier.name.startswith(self.start): return False
            return True
        def create(self, obj:Object):
            modifier = obj.modifiers.new(self.name, self.type)
            self.setup(modifier)
            return modifier

    class Snapshot:
        exclude = ('__', 'bl_', 'rna_', 'type')
        def __init__(self, obj:Object, modifier:Modifier):
            self.obj = obj
            self.modifier = modifier
            self.name = modifier.name
            self.properties = dict(
                # (p, getattr(modifier, copy(p))) for p in dir(modifier) if not any(p.startswith(e) for e in self.exclude)
                # (p, getattr(modifier, copy(p))) for p in dir(modifier) if not modifier.is_property_readonly(p) and not any(p.startswith(e) for e in self.exclude)
                (p, getattr(modifier, copy(p))) for (p, value) in modifier.bl_rna.properties.items() if not value.is_readonly
            )

    def __init__(self):
        self.running = False
        self.objects = []
        self.requests = []
        self.snapshots = {} # {object_name: [snapshot, ]}
        self.modifiers = {} # {object_name: [modifier, ]}
        self.reverse = False
        self.sort = False

    def begin(self, objects:List[Object], reverse=True, sort=False):
        if self.running: self.end()
        self.running = True
        self.reverse = reverse
        self.sort = sort
        self.objects = objects
        self.requests = []
        self.snapshots = {}
        self.modifiers = {}
    
    def end(self, search=True):
        '''
            search - search for existed modifiers
        '''
        self.running = False
        active = bpy.context.view_layer.objects.active

        # Creating snapshots, creating/searching modifiers, sorting it
        for obj in self.objects:
            bpy.context.view_layer.objects.active = obj
            self.snapshots.update({
                obj.name: [self.Snapshot(obj, m) for m in obj.modifiers]
            })
            modifiers = None
            sort = self.sort
            # Searching for existed modifiers
            if search:
                for i, modifier in enumerate(obj.modifiers):
                    modifiers = self.__search__(obj, -(i + 1) if self.reverse else i)
                    if modifiers: break
            # There are not existed modifiers combination, creating new
            if not modifiers:
                modifiers = [r.create(obj) for r in self.requests]
                sort = True
            # Sorting modifiers
            if sort:
                for m in modifiers: bubble_modifier(obj, m, reverse = self.reverse)
            self.modifiers.update({obj.name: modifiers})
            
        bpy.context.view_layer.objects.active = active
        return self.modifiers

    def apply(self):
        for obj in self.objects:
            for (modifier, command) in zip(self.modifiers[obj.name], self.requests):
                command.apply(modifier)
        return self

    def modifier(self, type:str, name=None, start='', order=True, setup=lambda m: None, apply=lambda m: None):
        if name is None: name = to_camel_case(type)
        self.requests.append(self.Command(
            name = name,
            type = type,
            start = start,
            order = order,
            setup = setup,
            apply = apply
        ))
        return self

    def undo(self):
        # Exclude modifiers that object doesn't contained at the snapshot moment
        for obj in self.objects:
            exclude = [m for m in obj.modifiers if not any(m.name == s.name for s in self.snapshots[obj.name])]
            for m in exclude: obj.modifiers.remove(m)
        # Restore order / sort
        for obj in self.objects:
            for i, snapshot in enumerate(self.snapshots[obj.name]):
                while obj.modifiers[i].name != snapshot.name:
                    bpy.ops.object.modifier_move_up(modifier = snapshot.name)
        # Restore parameters
        for snapshots in self.snapshots.values():
            for snapshot in snapshots:
                for (name, value) in snapshot.properties.items():
                    setattr(snapshot.modifier, name, value)
        return self


    def __search__(self, obj:Object, index:int):
        commands = iter(self.requests)
        current = next(commands)
        queue = []
        for modifier in obj.modifiers[index:]:
            if current == modifier:
                queue.append(modifier)
                current = next(commands)
            elif current.order:
                break
        if len(queue) == len(self.requests): return queue



# class PollsCollection:
#     @classmethod
#     def




class LinearArrayModifier(Operator):
    bl_idname = 'nextmd.linear_array'
    bl_label = 'Linear Array Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        if not context.active_object.select_get(): return False
        if context.active_object.type != 'MESH': return False
        return True

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)
        self.array = context.active_object.modifiers.new('LinearArray', 'ARRAY')
        self.array.merge_threshold = 10e-3
        
        self.axis = 'X'
        self.factor = 1.0

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Count', 'Ctrl+Scroll', lambda: self.array.count)
        self.pane.prop('Offset', 'Shift+Mouse', lambda: self.factor)
        self.pane.prop('Relative', 'R', lambda: self.array.use_relative_offset)
        self.pane.prop('Axis', 'X/Y/Z', lambda: self.axis)
        self.pane.prop('Merge', 'M', lambda: self.array.use_merge_vertices)
        self.pane.prop('Start Cap', 'Q', lambda: None if self.array.start_cap is None else self.array.start_cap.name)
        self.pane.prop('End Cap', 'E', lambda: None if self.array.end_cap is None else self.array.end_cap.name)
        self.pane.end()
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        def update():
            if self.array.use_relative_offset:
                self.array.relative_offset_displace.x = (self.factor if self.axis == 'X' else  0)
                self.array.relative_offset_displace.y = (self.factor if self.axis == 'Y' else  0)
                self.array.relative_offset_displace.z = (self.factor if self.axis == 'Z' else  0)
            else:
                self.array.constant_offset_displace.x = (self.factor if self.axis == 'X' else  0)
                self.array.constant_offset_displace.y = (self.factor if self.axis == 'Y' else  0)
                self.array.constant_offset_displace.z = (self.factor if self.axis == 'Z' else  0)

        

        # Inverting axis if it has been called twice
        if self.axis == event.type and event.value == 'PRESS':
            self.factor *= -1
            update()

        if event.type == 'MOUSEMOVE':
            self.execute(context)
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.factor += (event.mouse_x - event.mouse_prev_x) / 100
                update()
        elif event.type == 'X':
            self.axis = 'X'
            update()
        elif event.type == 'Y':
            self.axis = 'Y'
            update()
        elif event.type == 'Z':
            self.axis = 'Z'
            update()
        elif event.type == 'R' and event.value == 'PRESS':
            self.array.use_constant_offset = self.array.use_relative_offset
            self.array.use_relative_offset = not self.array.use_relative_offset
            update()
        elif event.type == 'WHEELUPMOUSE' and event.ctrl:
            self.array.count += 1
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl:
            self.array.count -= 1
        elif event.type == 'M' and event.value == 'PRESS':
            self.array.use_merge_vertices = not self.array.use_merge_vertices
        elif event.type == 'Q' and event.value == 'PRESS':
            self.array.start_cap = eyedropper(
                context, event.mouse_region_x, event.mouse_region_y, context.active_object
            )
        elif event.type == 'E' and event.value == 'PRESS':
            self.array.end_cap = eyedropper(
                context, event.mouse_region_x, event.mouse_region_y, context.active_object
            )

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            context.active_object.modifiers.remove(self.array)
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class CurveArrayModifier(Operator):
    bl_idname = 'nextmd.curve_array'
    bl_label = 'Curve Array Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if len(context.selected_objects) != 2: return False
        target, curve = context.selected_objects
        if target.type == 'CURVE': target, curve = curve, target
        if target.type != 'MESH' or curve.type != 'CURVE': return False
        return True

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)
        target, curve = context.selected_objects
        if target.type == 'CURVE': target, curve = curve, target
        self.target = target
        self.array = target.modifiers.new('CurveArray', 'ARRAY')
        self.array.fit_type = 'FIT_CURVE'
        self.array.curve = curve
        self.array.merge_threshold = 10e-3
        self.curve = target.modifiers.new('CurveDeformation', 'CURVE')
        self.curve.object = curve

        self.factor = 1.0

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Offset', 'Shift+Mouse', lambda: self.factor)
        self.pane.prop('Relative', 'R', lambda: self.array.use_relative_offset)
        self.pane.prop('Axis', 'X/Y/Z', lambda: self.curve.deform_axis.replace('POS_', '').replace('NEG_', '-'))
        self.pane.prop('Merge', 'M', lambda: self.array.use_merge_vertices)
        self.pane.prop('Start Cap', 'Q', lambda: None if self.array.start_cap is None else self.array.start_cap.name)
        self.pane.prop('End Cap', 'E', lambda: None if self.array.end_cap is None else self.array.end_cap.name)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        def update():
            axis = self.curve.deform_axis.replace('POS_', '').replace('NEG_', '')
            if self.array.use_relative_offset:
                self.array.relative_offset_displace.x = (self.factor if axis == 'X' else  0)
                self.array.relative_offset_displace.y = (self.factor if axis == 'Y' else  0)
                self.array.relative_offset_displace.z = (self.factor if axis == 'Z' else  0)
            else:
                self.array.constant_offset_displace.x = (self.factor if axis == 'X' else  0)
                self.array.constant_offset_displace.y = (self.factor if axis == 'Y' else  0)
                self.array.constant_offset_displace.z = (self.factor if axis == 'Z' else  0)

        if event.type == 'MOUSEMOVE':
            self.execute(context)
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.factor += (event.mouse_x - event.mouse_prev_x) / 100
                update()
        elif event.type == 'X' and event.value == 'PRESS':
            self.curve.deform_axis = 'NEG_X' if self.curve.deform_axis == 'POS_X' else 'POS_X'
            update()
        elif event.type == 'Y' and event.value == 'PRESS':
            self.curve.deform_axis = 'NEG_Y' if self.curve.deform_axis == 'POS_Y' else 'POS_Y'
            update()
        elif event.type == 'Z' and event.value == 'PRESS':
            self.curve.deform_axis = 'NEG_Z' if self.curve.deform_axis == 'POS_Z' else 'POS_Z'
            update()
        elif event.type == 'R' and event.value == 'PRESS':
            self.array.use_constant_offset = self.array.use_relative_offset
            self.array.use_relative_offset = not self.array.use_relative_offset
            update()
        elif event.type == 'M' and event.value == 'PRESS':
            self.array.use_merge_vertices = not self.array.use_merge_vertices
        elif event.type == 'Q' and event.value == 'PRESS':
            self.array.start_cap = eyedropper(
                context, event.mouse_region_x, event.mouse_region_y, context.active_object
            )
        elif event.type == 'E' and event.value == 'PRESS':
            self.array.end_cap = eyedropper(
                context, event.mouse_region_x, event.mouse_region_y, context.active_object
            )

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            self.target.modifiers.remove(self.array)
            self.target.modifiers.remove(self.curve)
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class RadialArrayModifier(Operator):
    bl_idname = 'nextmd.radial_array'
    bl_label = 'Radial Array Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if len(context.selected_objects) > 2: return False
        if len(context.selected_objects) == 0: return False
        if bpy.context.active_object is None: return False
        if not context.active_object.select_get(): return False
        return True

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)
        if len(context.selected_objects) == 1:
            self.empty = bpy.data.objects.new('RadialArrayEmpty', object_data = None)
            self.empty.matrix_world = context.scene.cursor.matrix
            # self.empty.empty_display_type = 'CIRCLE'
            context.collection.objects.link(self.empty)
            self.target = context.active_object
            # self.empty.empty_display_size = (self.target.matrix_world.translation - self.empty.matrix_world.translation).length
            self.has_empty = False
        else:
            self.empty = context.active_object
            self.target = context.selected_objects[0] if context.selected_objects[1] == self.empty else context.selected_objects[1]
            self.has_empty = True
        # Сохранняем состояние для того чтобы потом его восстановить
        self.target_matrix = self.target.matrix_world.copy()
        self.empty_matrix = self.empty.matrix_world.copy()
        self.cursor_matrix = context.scene.cursor.matrix.copy()
        
        self.empty.select_set(False)
        context.view_layer.objects.active = self.target
        context.scene.cursor.location = self.empty.matrix_world.translation
        bpy.ops.object.origin_set(type = 'ORIGIN_CURSOR')
        self.empty.matrix_world = self.target.matrix_world
        self.displace = self.target.modifiers.new('Displace', 'DISPLACE')
        self.displace.direction = 'X'
        self.displace.strength = 0
        self.array = self.target.modifiers.new('RadialArray', 'ARRAY')
        self.array.merge_threshold = 10e-3
        self.array.count = 1
        self.array.use_relative_offset = False
        self.array.use_object_offset = True
        self.array.offset_object = self.empty
        self.transform = self.empty.matrix_world.copy()
        self.empty.select_set(True)
        
        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Count', 'Ctrl+Scroll', lambda: self.array.count)
        self.pane.prop('Offset', 'Shift+Mouse', lambda: self.displace.strength)
        self.pane.prop('Merge', 'M', lambda: self.array.use_merge_vertices)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        def update():
            context.view_layer.objects.active = self.empty
            self.empty.matrix_world = self.transform.copy()
            self.empty.matrix_world @= Matrix.Rotation(radians(360 / self.array.count), 4, 'Z')

        if event.type == 'MOUSEMOVE':
            self.execute(context)
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.displace.strength += (event.mouse_x - event.mouse_prev_x) / 100
        elif event.type == 'WHEELUPMOUSE' and event.ctrl:
            self.array.count += 1
            update()
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl:
            self.array.count -= 1
            update()
        elif event.type == 'M' and event.value == 'PRESS':
            self.array.use_merge_vertices = not self.array.use_merge_vertices

        elif event.type == 'LEFTMOUSE':
            # Восстанавливаем курсор
            context.scene.cursor.matrix = self.cursor_matrix
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            self.empty.select_set(False)
            # Восстанавливаем объект
            context.scene.cursor.matrix = self.target_matrix
            context.view_layer.objects.active = self.target
            bpy.ops.object.origin_set(type = 'ORIGIN_CURSOR')
            # Восстанавливаем пустышку
            self.empty.select_set(True)
            context.view_layer.objects.active = self.empty
            self.empty.matrix_world = self.empty_matrix
            if not self.has_empty:
                bpy.data.objects.remove(self.empty)
                context.view_layer.objects.active = self.target
            # Восстанавливаем модификаторы
            self.target.modifiers.remove(self.displace)
            self.target.modifiers.remove(self.array)
            # Восстанавливаем курсор
            context.scene.cursor.matrix = self.cursor_matrix
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class MirrorModifier(Operator):
    bl_idname = 'nextmd.mirror'
    bl_label = 'Mirror Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        if not context.active_object.select_get(): return False
        if context.active_object.type != 'MESH': return False
        return True

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        for obj in context.selected_objects:
            obj.select_set(obj is context.active_object)

        self.mirror = context.active_object.modifiers.new('Mirror', 'MIRROR')
        self.mirror.use_bisect_axis = (True, True, True)
        
        def to_axis():
            return f'{"-" if self.mirror.use_bisect_flip_axis[0] and self.mirror.use_axis[0] else ""}{"X" if self.mirror.use_axis[0] else ""}' + \
                f'{"-" if self.mirror.use_bisect_flip_axis[1] and self.mirror.use_axis[1] else ""}{"Y" if self.mirror.use_axis[1] else ""}' + \
                f'{"-" if self.mirror.use_bisect_flip_axis[2] and self.mirror.use_axis[2] else ""}{"Z" if self.mirror.use_axis[2] else ""}'

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Axis', 'X/Y/Z', to_axis, subtype = 'AXIS')
        self.pane.prop('Bisect', 'T', lambda: any(self.mirror.use_bisect_axis))
        self.pane.prop('Clip', 'C', lambda: self.mirror.use_clip)
        self.pane.prop('Merge', 'M', lambda: self.mirror.use_mirror_merge)
        self.pane.prop('Mirror Object', 'E', lambda: None if self.mirror.mirror_object is None else self.mirror.mirror_object.name)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.execute(context)
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
        elif event.type == 'X' and event.value == 'PRESS':
            if self.mirror.use_axis[0] == False:
                self.mirror.use_axis[0] = True
                self.mirror.use_bisect_flip_axis[0] = False
            elif self.mirror.use_bisect_flip_axis[0] == False:
                self.mirror.use_bisect_flip_axis[0] = True
            else:
                self.mirror.use_axis[0] = False
                self.mirror.use_bisect_flip_axis[0] = False
        elif event.type == 'Y' and event.value == 'PRESS':
            if self.mirror.use_axis[1] == False:
                self.mirror.use_axis[1] = True
                self.mirror.use_bisect_flip_axis[1] = False
            elif self.mirror.use_bisect_flip_axis[1] == False:
                self.mirror.use_bisect_flip_axis[1] = True
            else:
                self.mirror.use_axis[1] = False
                self.mirror.use_bisect_flip_axis[1] = False
        elif event.type == 'Z' and event.value == 'PRESS':
            if self.mirror.use_axis[2] == False:
                self.mirror.use_axis[2] = True
                self.mirror.use_bisect_flip_axis[2] = False
            elif self.mirror.use_bisect_flip_axis[2] == False:
                self.mirror.use_bisect_flip_axis[2] = True
            else:
                self.mirror.use_axis[2] = False
                self.mirror.use_bisect_flip_axis[2] = False
        elif event.type == 'T' and event.value == 'PRESS':
            self.mirror.use_bisect_axis = (not any(self.mirror.use_bisect_axis), ) * 3
        elif event.type == 'M' and event.value == 'PRESS':
            self.mirror.use_mirror_merge = not self.mirror.use_mirror_merge
        elif event.type == 'C' and event.value == 'PRESS':
            self.mirror.use_clip = not self.mirror.use_clip
        elif event.type == 'E' and event.value == 'PRESS':
            self.mirror.mirror_object = eyedropper(
                context, event.mouse_region_x, event.mouse_region_y, context.active_object
            )

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            context.active_object.modifiers.remove(self.mirror)
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}



class DisplaceModifier(Operator):
    bl_idname = 'nextmd.displace'
    bl_label = 'Displace Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        if not context.active_object.select_get(): return False
        if context.active_object.type != 'MESH': return False
        return True

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.displace = context.active_object.modifiers.new('Displace', 'DISPLACE')

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Offset', 'Shift+Mouse', lambda: self.displace.strength)
        self.pane.prop('Direction', 'Alt+Scroll', lambda: self.displace.direction.replace('_', ' '))
        self.pane.prop('Local', 'R', lambda: self.displace.space == 'LOCAL')
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        direction = [
            'X', 'Y', 'Z',
            'NORMAL',
            'CUSTOM_NORMAL',
            'RGB_TO_XYZ'
        ]

        if event.type == 'MOUSEMOVE':
            self.execute(context)
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.displace.strength += (event.mouse_x - event.mouse_prev_x) / 100
        elif event.type == 'WHEELUPMOUSE' and event.alt:
            index = direction.index(self.displace.direction)
            self.displace.direction = direction[(index - 1) % len(direction)]
        elif event.type == 'WHEELDOWNMOUSE' and event.alt:
            index = direction.index(self.displace.direction)
            self.displace.direction = direction[(index + 1) % len(direction)]
        elif event.type == 'R' and event.value == 'PRESS':
            self.displace.space = 'GLOBAL' if self.displace.space == 'LOCAL' else 'LOCAL'

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            context.active_object.modifiers.remove(self.displace)
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}



class AlignViewportTool(Operator):
    bl_idname = 'nextmd.align_viewport'
    bl_label = 'Align Viewport'
    bl_options = {'REGISTER', 'UNDO'}

    axis: StringProperty('Axis', default = 'Z')

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        if len(context.selected_objects) == 0: return False
        return True

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.matrixes = [o.matrix_world.copy() for o in context.selected_objects]

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Axis', 'X/Y/Z', lambda: self.axis)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        viewport = context.space_data.region_3d.view_matrix.inverted()
        for obj, matrix in zip(context.selected_objects, self.matrixes):
            l, r, s = matrix.decompose()
            direction = (viewport.translation - l) if context.space_data.region_3d.is_perspective else viewport.to_3x3() @ Vector((0, 0, 1))
            if self.axis == 'X' or self.axis == '-X':
                track = direction.to_track_quat(self.axis, 'Z')
            elif self.axis == 'Y' or self.axis == '-Y':
                track = direction.to_track_quat(self.axis, 'Z')
            elif self.axis == 'Z' or self.axis == '-Z':
                track = direction.to_track_quat(self.axis, 'Y')
            obj.matrix_world = Matrix.Translation(l) @ track.to_matrix().to_4x4() @ Matrix.Scale(1, 4, s)
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.execute(context)
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
        elif event.type == 'X' and event.value == 'PRESS':
            self.axis = '-X' if self.axis == 'X' else 'X'
            self.execute(context)
        elif event.type == 'Y' and event.value == 'PRESS':
            self.axis = '-Y' if self.axis == 'Y' else 'Y'
            self.execute(context)
        elif event.type == 'Z' and event.value == 'PRESS':
            self.axis = '-Z' if self.axis == 'Z' else 'Z'
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            for obj, matrix in zip(context.selected_objects, self.matrixes):
                obj.matrix_world = matrix
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}



class BooleanModifier(Operator):
    bl_idname = 'nextmd.boolean'
    bl_label = 'Boolean Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    operation: StringProperty(default = 'DIFFERENCE')
    hidden: BoolProperty(default = True)
    exact: BoolProperty(default = False)

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        if not context.active_object.select_get(): return False
        if len(context.selected_objects) <= 1: return False
        if context.active_object.type != 'MESH': return False
        return True

    def draw(self, context:Context):
        pass

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.clipping = [o for o in context.selected_objects if o is not context.active_object]
        self.booleans = [context.active_object.modifiers.new('Boolean', 'BOOLEAN') for o in self.clipping]
        for obj, modifier in zip(self.clipping, self.booleans):
            modifier.object = obj

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Operation', 'Q(Inter) / W(Union) / E(Diff)', lambda: self.operation)
        self.pane.prop('Hide Objects', 'R', lambda: self.hidden)
        self.pane.prop('Exact', 'F', lambda: self.exact)
        self.pane.end()

        self.execute(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        for obj, modifier in zip(self.clipping, self.booleans):
            modifier.operation = self.operation
            modifier.solver = 'EXACT' if self.exact else 'FAST'
            obj.display_type = 'WIRE' if self.hidden else 'TEXTURED'
            obj.hide_render = self.hidden
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
        elif event.type == 'Q' and event.value == 'PRESS':
            self.operation = 'INTERSECT'
            self.execute(context)
        elif event.type == 'W' and event.value == 'PRESS':
            self.operation = 'UNION'
            self.execute(context)
        elif event.type == 'E' and event.value == 'PRESS':
            self.operation = 'DIFFERENCE'
            self.execute(context)
        elif event.type == 'R' and event.value == 'PRESS':
            self.hidden = not self.hidden
            self.execute(context)
        elif event.type == 'F' and event.value == 'PRESS':
            self.exact = not self.exact
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            for obj, modifier in zip(self.clipping, self.booleans):
                context.active_object.modifiers.remove(modifier)
                obj.hide_render = False
                obj.display_type = 'TEXTURED'
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class ApplyModifiersTool(Operator):
    bl_idname = 'nextmd.apply_modifiers'
    bl_label = 'Apply Modifiers'
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(items = [
        ('KEEP', 'Keep', ''),
        ('REMOVE', 'Remove', ''),
        ('MODIFY', 'Modify', '')
    ])
    boolean: BoolProperty(default = True)
    subsurf: BoolProperty(default = True)
    mirror: BoolProperty(default = True)
    weighted_normal: BoolProperty(default = True)
    other: BoolProperty(default = True)

    @classmethod
    def poll(cls, context:Context):
        if not context.selected_objects: return False
        return True

    def draw(self, context:Context):
        layout = self.layout
        layout.prop(self, 'mode', text = 'Mode')
        layout.prop(self, 'boolean', text = 'Apply Boolean')
        layout.prop(self, 'subsurf', text = 'Apply Subdivision Surface')
        layout.prop(self, 'mirror', text = 'Apply Mirror')
        layout.prop(self, 'weighted_normal', text = 'Apply Weighted Normals')
        layout.prop(self, 'other', text = 'Apply Other Modifiers')

    def execute(self, context:Context):
        active = context.active_object
        def is_excess(modifier:Modifier):
            if modifier.type == 'BOOLEAN' and self.boolean: return True
            if modifier.type == 'SUBSURF' and self.subsurf: return True
            if modifier.type == 'MIRROR' and self.mirror: return True
            if modifier.type == 'WEIGHTED_NORMAL' and self.weighted_normal: return True
            if modifier.type not in ('BOOLEAN', 'SUBSURF', 'MIRROR', 'WEIGHTED_NORMAL') and self.other: return True
            return False
        to_remove = []
        for obj in context.selected_objects:
            context.view_layer.objects.active = obj
            excess = [m for m in obj.modifiers if is_excess(m)]
            for modifier in excess:
                if self.mode == 'REMOVE':
                    if modifier.type == 'BOOLEAN':
                        to_remove.append(modifier.object)
                    elif modifier.type == 'MIRROR' and modifier.mirror_object is not None:
                        to_remove.append(modifier.mirror_object)
                
                elif self.mode == 'MODIFY':
                    if modifier.type == 'BOOLEAN' and modifier.operation == 'DIFFERENCE' and modifier.object is not None:
                        clipper = modifier.object
                        modifier.show_viewport = False
                        context.view_layer.objects.active = clipper
                        m = clipper.modifiers.new('Boolean', 'BOOLEAN')
                        m.operation = 'INTERSECT'
                        m.object = obj
                        clipper.display_type = 'TEXTURED'
                        bpy.ops.object.modifier_apply(modifier = m.name)
                        modifier.show_viewport = True
                        modifier.solver = 'EXACT'
                        context.view_layer.objects.active = obj
 
                bpy.ops.object.modifier_apply(modifier = modifier.name)
        for obj in to_remove: bpy.data.objects.remove(obj)
        context.view_layer.objects.active = active
        return {'FINISHED'}




class SmoothSharp(Operator):
    bl_idname = 'nextmd.smooth_sharp'
    bl_label = 'Smooth Sharp Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    width: FloatProperty(default = 0.1, min = 0)
    segments: IntProperty(default = 2, min = 1)
    profile: FloatProperty(default = 0.5, min = 0, max = 1)
    angle: IntProperty(default = 60, min = 1, max = 180)
    harden_normals: BoolProperty(default = True)

    @classmethod
    def poll(cls, context:Context):
        if len(context.selected_objects) == 0: return False
        return True

    def draw(self, context:Context):
        pass

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.bevels = dict((o, o.modifiers.new('SmoothSharp', 'BEVEL')) for o in context.selected_objects)
        self.auto_smooth = [o.data.use_auto_smooth for o in self.bevels]
        for (obj, modifier) in self.bevels.items():
            modifier.miter_outer = 'MITER_ARC'
            modifier.use_clamp_overlap = False
            obj.show_all_edges = True
            obj.show_wire = True

        self.mode = context.mode
        bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Width', 'Shift+Mouse', lambda: self.width)
        self.pane.prop('Segments', 'Ctrl+Scroll', lambda: self.segments)
        self.pane.prop('Profile', 'Alt+Mouse / Q(0.3) / W(0.5) / E(0.75)', lambda: self.profile)
        self.pane.prop('Angle', 'Alt+Scroll', lambda: self.angle)
        self.pane.prop('Harden Normals', 'F', lambda: self.harden_normals)
        self.pane.end()

        self.execute(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        for (obj, modifier) in self.bevels.items():
            modifier.width = self.width
            modifier.segments = self.segments
            modifier.profile = self.profile
            modifier.angle_limit = radians(self.angle)
            modifier.harden_normals = self.harden_normals
            obj.data.use_auto_smooth = self.harden_normals
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.width += (event.mouse_x - event.mouse_prev_x) / 100
                self.execute(context)
            if event.alt:
                self.profile += (event.mouse_x - event.mouse_prev_x) / 100
                self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and event.ctrl:
            self.segments += 1
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl:
            self.segments -= 1
            self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and event.alt:
            self.angle += 5
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.alt:
            self.angle -= 5
            self.execute(context)
        elif event.type == 'Q' and event.value == 'PRESS':
            self.profile = 0.3
            self.execute(context)
        elif event.type == 'W' and event.value == 'PRESS':
            self.profile = 0.5
            self.execute(context)
        elif event.type == 'E' and event.value == 'PRESS':
            self.profile = 0.75
            self.execute(context)
        elif event.type == 'F' and event.value == 'PRESS':
            self.harden_normals = not self.harden_normals
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            if self.mode == 'EDIT_MESH': bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
            for (obj, modifier) in self.bevels.items():
                obj.show_all_edges = False
                obj.show_wire = False
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            for auto_smooth, (obj, modifier) in zip(self.auto_smooth, self.bevels.items()):
                obj.data.use_auto_smooth = auto_smooth
                obj.modifiers.remove(modifier)
                obj.show_all_edges = False
                obj.show_wire = False
            if self.mode == 'EDIT_MESH': bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}



'''
selected && edit = edge weight
# selected && object = edge weight + modifier
!crease = detect + modifier weight
crease = modifier weight
'''
class BevelModifier(Operator):
    bl_idname = 'nextmd.bevel'
    bl_label = 'Bevel Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    width: FloatProperty(default = 0.4, min = 0)
    segments: IntProperty(default = 1, min = 1)
    profile: FloatProperty(default = 0.5, min = 0, max = 1)
    angle: IntProperty(default = 85, min = 1, max = 180)
    union: IntProperty(default = 145, min = 1, max = 180)
    harden_normals: BoolProperty(default = False)

    @classmethod
    def poll(cls, context:Context):
        if len(context.selected_objects) == 0: return False
        return True

    def draw(self, context:Context):
        pass

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        active = context.active_object
        self.mode = context.mode
        bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
        bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)
        self.selected = any(any(e.select for e in o.data.edges) for o in context.selected_objects)
        self.crease = any(any(e.bevel_weight > 10e-3 for e in o.data.edges) for o in context.selected_objects)
        self.factor = 0.0
        bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)
        if self.selected and self.mode == 'EDIT_MESH': self.method = 'EDGE'
        elif not self.crease: self.method = 'DETECT'
        else: self.method = 'MODIFIER'

        self.bevels = []
        for obj in context.selected_objects:
            modifier = next(reversed([m for m in obj.modifiers if m.type == 'BEVEL' and m.limit_method == 'WEIGHT']), None)
            weights = [e.bevel_weight for e in obj.data.edges]
            if modifier is None:
                modifier = obj.modifiers.new('Bevel', 'BEVEL')
                modifier.miter_outer = 'MITER_ARC'
                modifier.use_clamp_overlap = False
                modifier.limit_method = 'WEIGHT'
                self.bevels.append((obj, modifier, False, obj.data.use_auto_smooth, weights, modifier.width))
            else:
                self.bevels.append((obj, modifier, True, obj.data.use_auto_smooth, weights, modifier.width))
            modifier.width = self.width

            if self.method == 'DETECT':
                context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
                indexes = detect(radians(self.angle), radians(self.union), radians(110))
                bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)
                for index in indexes: obj.data.edges[index].bevel_weight = 1

        for obj, modifier, existed, smooth, weights, width in self.bevels:
            obj.show_all_edges = True
            obj.show_wire = True

        def max_edge_width():
            return max(max(e.bevel_weight for e in o.data.edges) for o in context.selected_objects)

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Width', 'Shift+Mouse', lambda: (max_edge_width() if self.method == 'EDGE' else self.width))
        self.pane.prop('Segments', 'Ctrl+Scroll', lambda: self.segments)
        self.pane.prop('Profile', 'Alt+Mouse / Q(0.3) / W(0.5) / E(0.75)', lambda: self.profile)
        # self.pane.prop('Angle', 'Alt+Scroll', lambda: self.angle)
        # self.pane.prop('Union', 'Alt+Ctrl+Scroll', lambda: self.union)
        self.pane.prop('Harden Normals', 'F', lambda: self.harden_normals)
        self.pane.end()

        context.view_layer.objects.active = active
        self.execute(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        for obj, modifier, existed, smooth, weights, width in self.bevels:
            modifier.segments = self.segments
            modifier.profile = self.profile
            modifier.harden_normals = self.harden_normals
            obj.data.use_auto_smooth = self.harden_normals
            if self.method == 'EDGE':
                for edge in obj.data.edges:
                    if not edge.select: continue
                    edge.bevel_weight += self.factor
            else:
                modifier.width = self.width
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                if self.method == 'EDGE':
                    self.factor = (event.mouse_x - event.mouse_prev_x) / 25
                else:
                    self.width += (event.mouse_x - event.mouse_prev_x) / 100
                self.execute(context)
            if event.alt:
                self.profile += (event.mouse_x - event.mouse_prev_x) / 100
                self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and event.ctrl and not event.alt:
            self.segments += 1
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl and not event.alt:
            self.segments -= 1
            self.execute(context)
        # elif event.type == 'WHEELUPMOUSE' and event.alt and not event.ctrl:
        #     self.angle += 5
        #     self.execute(context)
        # elif event.type == 'WHEELDOWNMOUSE' and event.alt and not event.ctrl:
        #     self.angle -= 5
        #     self.execute(context)
        # elif event.type == 'WHEELUPMOUSE' and event.alt and event.ctrl:
        #     self.union += 5
        #     self.execute(context)
        # elif event.type == 'WHEELDOWNMOUSE' and event.alt and event.ctrl:
            self.union -= 5
            self.execute(context)
        elif event.type == 'Q' and event.value == 'PRESS':
            self.profile = 0.3
            self.execute(context)
        elif event.type == 'W' and event.value == 'PRESS':
            self.profile = 0.5
            self.execute(context)
        elif event.type == 'E' and event.value == 'PRESS':
            self.profile = 0.75
            self.execute(context)
        elif event.type == 'F' and event.value == 'PRESS':
            self.harden_normals = not self.harden_normals
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            if self.mode == 'EDIT_MESH': bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
            for obj, modifier, existed, smooth, weights, width in self.bevels:
                obj.show_all_edges = False
                obj.show_wire = False
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            for obj, modifier, existed, smooth, weights, width in self.bevels:
                obj.data.use_auto_smooth = smooth
                modifier.width = width
                if not existed: obj.modifiers.remove(modifier)
                for edge, weight in zip(obj.data.edges, weights): edge.bevel_weight = weight
                obj.show_all_edges = False
                obj.show_wire = False
            if self.mode == 'EDIT_MESH': bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
            return {'CANCELLED'}

        if event.value == 'RELEASE':
            self.pane.flush()

        self.factor = 0.0
        return {'RUNNING_MODAL'}


class CreaseSharpTool(Operator):
    bl_idname = 'nextmd.crease_sharp'
    bl_label = 'Crease Sharp'
    bl_options = {'REGISTER', 'UNDO'}

    angle: IntProperty(default = 85, min = 1, max = 180)
    union: IntProperty(default = 145, min = 1, max = 180)
    limit: IntProperty(default = 110, min = 1, max = 180)
    sharp: BoolProperty(default = True)
    crease: FloatProperty(default = 1, min = 0, max = 1)
    seam: BoolProperty(default = True)
    clear: BoolProperty(default = True)

    @classmethod
    def poll(cls, context:Context):
        if len(context.selected_objects) == 0: return False
        return True

    def draw(self, context:Context):
        layout = self.layout
        layout.prop(self, 'angle', text = 'Crease Angle')
        layout.prop(self, 'union', text = 'Union Angle')
        layout.prop(self, 'limit', text = 'Break Angle')
        layout.prop(self, 'sharp', text = 'Mark Sharp')
        layout.prop(self, 'crease', text = 'Edge Crease')
        layout.prop(self, 'seam', text = 'Mark Seam')
        layout.prop(self, 'clear', text = 'Clear And Mark')

    def invoke(self, context:Context, event:Event):
        self.mode = context.mode
        bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)
        self.selected = any(any(e.select for e in o.data.edges) for o in context.selected_objects)
        if self.selected and context.mode == 'EDIT_MESH':
            self.clear = False
        return self.execute(context)

    def execute(self, context:Context):
        active = context.active_object
        for obj in context.selected_objects:
            context.view_layer.objects.active = obj
            
            if self.clear:
                bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)
                for edge in obj.data.edges:
                    edge.use_edge_sharp = False
                    edge.crease = 0
                    edge.use_seam = False
            
            if self.selected and self.mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)
                for edge in obj.data.edges:
                    if not edge.select: continue
                    edge.use_edge_sharp = self.sharp
                    edge.crease = self.crease
                    edge.use_seam = self.seam
            
            else:
                bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
                indexes = detect(radians(self.angle), radians(self.union), radians(self.limit))
                bpy.ops.object.mode_set(mode = 'OBJECT', toggle = False)
                for index in indexes:
                    edge = obj.data.edges[index]
                    edge.use_edge_sharp = self.sharp
                    edge.crease = self.crease
                    edge.use_seam = self.seam

        context.view_layer.objects.active = active

        if self.mode == 'EDIT_MESH': bpy.ops.object.mode_set(mode = 'EDIT', toggle = False)
        return {'FINISHED'}



class SolidifyModifier(Operator):
    bl_idname = 'nextmd.solidify'
    bl_label = 'Solidify Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        return True

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.solidify = context.active_object.modifiers.new('Solidify', 'SOLIDIFY')
        self.solidify.use_even_offset = True

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Thickness', 'Shift+Mouse', lambda: self.solidify.thickness)
        self.pane.prop('Offset', 'Alt+Mouse', lambda: self.solidify.offset)
        self.pane.prop('Fill', 'Q', lambda: self.solidify.use_rim)
        self.pane.prop('Only Rim', 'E', lambda: self.solidify.use_rim_only)
        self.pane.prop('Flip Normals', 'R', lambda: self.solidify.use_flip_normals)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.execute(context)
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.solidify.thickness += (event.mouse_x - event.mouse_prev_x) / 100
            if event.alt:
                self.solidify.offset += (event.mouse_x - event.mouse_prev_x) / 100
        elif event.type == 'Q' and event.value == 'PRESS':
            self.solidify.use_rim = not self.solidify.use_rim
        elif event.type == 'E' and event.value == 'PRESS':
            self.solidify.use_rim_only = not self.solidify.use_rim_only
        elif event.type == 'R' and event.value == 'PRESS':
            self.solidify.use_flip_normals = not self.solidify.use_flip_normals

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            context.active_object.modifiers.remove(self.solidify)
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class SubSurfModifier(Operator):
    bl_idname = 'nextmd.subsurf'
    bl_label = 'Subdivision Surface Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    hight_quality_render: BoolProperty(default = True)

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        return True

    def draw(self, context:Context):
        pass

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.subsurf = context.active_object.modifiers.new('Subsurf', 'SUBSURF')

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Levels', 'Ctrl+Mouse', lambda: self.subsurf.levels)
        self.pane.prop('High Quality Render', 'Q', lambda: self.hight_quality_render)
        self.pane.prop('Type', 'E', lambda: self.subsurf.subdivision_type.replace('_', ' '))
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        self.subsurf.render_levels = ((self.subsurf.levels + 1) if self.hight_quality_render else self.subsurf.levels)
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
        elif event.type == 'WHEELUPMOUSE' and event.ctrl:
            self.subsurf.levels += 1
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl:
            self.subsurf.levels -= 1
            self.execute(context)
        elif event.type == 'Q' and event.value == 'PRESS':
            self.hight_quality_render = not self.hight_quality_render
            self.execute(context)
        elif event.type == 'E' and event.value == 'PRESS':
            self.subsurf.subdivision_type = 'SIMPLE' if self.subsurf.subdivision_type == 'CATMULL_CLARK' else 'CATMULL_CLARK'

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            context.active_object.modifiers.remove(self.subsurf)
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class WeightedNormalModifier(Operator):
    bl_idname = 'nextmd.weighted_normal'
    bl_label = 'Weighted Normal Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if not context.selected_objects: return False
        return True

    def execute(self, context:Context):
        active = context.active_object
        for obj in context.selected_objects:
            obj.data.use_auto_smooth = True
            modifier = next(reversed([m for m in obj.modifiers if m.type == 'WEIGHTED_NORMAL']), None)
            if modifier is None:
                modifier = context.active_object.modifiers.new('WeightedNormal', 'WEIGHTED_NORMAL')
            context.view_layer.objects.active = obj
            while obj.modifiers[-1] != modifier:
                bpy.ops.object.modifier_move_down(modifier = modifier.name)
        context.view_layer.objects.active = active
        return {'FINISHED'}




class CurveModifier(Operator):
    bl_idname = 'nextmd.curve'
    bl_label = 'Curve Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    existed: BoolProperty(default = False)

    axis: EnumProperty(items = [
        ('POS_X', 'X', ''),
        ('NEG_X', '-X', ''),
        ('POS_Y', 'Y', ''),
        ('NEG_Y', '-Y', ''),
        ('POS_Z', 'Z', ''),
        ('NEG_Z', '-Z', ''),
    ])

    @classmethod
    def poll(cls, context:Context):
        objects, curves = get_objects(context, lambda o: o.type == 'MESH', lambda o: o.type == 'CURVE')
        if not objects: return False
        if len(curves) != 1: return False
        return True

    def draw(self, context:Context):
        layout = self.layout
        layout.prop(self, 'axis', text = 'Axis')

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)
        self.modifiers = ModifiersManager()

        self.objects, self.curves = get_objects(context, lambda o: o.type == 'MESH', lambda o: o.type == 'CURVE')

        def setup(modifier:CurveModifier):
            modifier.object = self.curves[0]
        def apply(modifier:CurveModifier):
            modifier.deform_axis = self.axis
        self.modifiers.begin(self.objects)
        self.modifiers.modifier('CURVE', 'Curve', setup = setup, apply = apply)
        self.modifiers.end(search = self.existed)

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Axis', 'X/Y/Z', lambda: self.axis.replace('POS_', '').replace('NEG_', '-'))
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        self.modifiers.apply()
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
        elif event.type == 'X' and event.value == 'PRESS':
            self.axis = 'NEG_X' if self.axis == 'POS_X' else 'POS_X'
            self.execute(context)
        elif event.type == 'Y' and event.value == 'PRESS':
            self.axis = 'NEG_Y' if self.axis == 'POS_Y' else 'POS_Y'
            self.execute(context)
        elif event.type == 'Z' and event.value == 'PRESS':
            self.axis = 'NEG_Z' if self.axis == 'POS_Z' else 'POS_Z'
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            self.modifiers.undo()
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}



class ScrewModifier(Operator):
    bl_idname = 'nextmd.screw'
    bl_label = 'Screw Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    existed: BoolProperty(default = False)

    screw_offset: FloatProperty(default = 0)
    resolution: IntProperty(default = 16, min = 1, max = 512)
    angle: IntProperty(default = 360)
    iterations: IntProperty(default = 1, min = 1, max = 100)
    axis: EnumProperty(items = [
        ('X', 'X', ''),
        ('Y', 'Y', ''),
        ('Z', 'Z', '')
    ], default = 'Z')
    merge: BoolProperty(default = True)
    object: StringProperty(default = '')

    @classmethod
    def poll(cls, context:Context):
        objects = get_objects(context, lambda o: o.type == 'MESH')
        if not objects: return False
        return True

    def draw(self, context:Context):
        layout = self.layout
        layout.prop(self, 'axis', text = 'Axis')

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)
        self.modifiers = ModifiersManager()

        self.objects = get_objects(context, lambda o: o.type == 'MESH')

        def apply(modifier:ScrewModifier):
            modifier.screw_offset = self.screw_offset
            modifier.steps = self.resolution
            modifier.render_steps = self.resolution
            modifier.angle = radians(self.angle)
            modifier.iterations = self.iterations
            modifier.axis = self.axis
            modifier.use_merge_vertices = self.merge
            modifier.object = bpy.data.objects[self.object] if self.object != '' else None
        def setup(modifier:ScrewModifier):
            modifier.use_normal_calculate = True
            apply(modifier)
        self.modifiers.begin(self.objects)
        self.modifiers.modifier('SCREW', 'Screw', setup = setup, apply = apply)
        self.modifiers.end(search = self.existed)

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Offset', 'Shift+Mouse', lambda: self.screw_offset)
        self.pane.prop('Resolution', 'Ctrl+Scroll', lambda: self.resolution)
        self.pane.prop('Angle', 'Alt+Scroll', lambda: self.angle)
        self.pane.prop('Iterations', 'Alt+Ctrl+Scroll', lambda: self.iterations)
        self.pane.prop('Axis', 'X/Y/Z', lambda: self.axis)
        self.pane.prop('Merge', 'M', lambda: self.merge)
        self.pane.prop('Axis Object', 'E', lambda: None if self.object == '' else self.object)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        self.modifiers.apply()
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.screw_offset += (event.mouse_x - event.mouse_prev_x) / 100
                self.execute(context)
        elif event.type == 'X':
            self.axis = 'X'
            self.execute(context)
        elif event.type == 'Y':
            self.axis = 'Y'
            self.execute(context)
        elif event.type == 'Z':
            self.axis = 'Z'
            self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and event.ctrl and not event.alt:
            self.resolution += 1
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl and not event.alt:
            self.resolution -= 1
            self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and event.alt and not event.ctrl:
            self.angle += 5
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.alt and not event.ctrl:
            self.angle -= 5
            self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and event.alt and event.ctrl:
            self.iterations += 1
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.alt and event.ctrl:
            self.iterations -= 1
            self.execute(context)
        elif event.type == 'C' and event.value == 'PRESS':
            self.merge = not self.merge
            self.execute(context)
        elif event.type == 'E' and event.value == 'PRESS':
            obj = eyedropper(
                context, event.mouse_region_x, event.mouse_region_y, self.objects
            )
            self.object = '' if obj is None else obj.name
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            self.modifiers.undo()
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}



class SimpleDeformModifier(Operator):
    bl_idname = 'nextmd.simple_deform'
    bl_label = 'Simple Deform Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    existed: BoolProperty(default = False)

    value: FloatProperty(default = radians(45))
    axis: EnumProperty(items = [
        ('X', 'X', ''),
        ('Y', 'Y', ''),
        ('Z', 'Z', '')
    ], default = 'X')
    deform_method: EnumProperty(items = [
        ('TWIST', 'Twist', ''),
        ('BEND', 'Bend', ''),
        ('TAPER', 'Taper', ''),
        ('STRETCH', 'Stretch', '')
    ], default = 'BEND')

    @classmethod
    def poll(cls, context:Context):
        objects = get_objects(context, lambda o: o.type == 'MESH')
        if not objects: return False
        return True

    def draw(self, context:Context):
        layout = self.layout
        layout.prop(self, 'value', text = 'Value')
        layout.prop(self, 'axis', text = 'Axis')
        layout.prop(self, 'deform_method', text = 'Deform Method')
        layout.prop(self, 'origin', text = 'Origin')

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)
        self.modifiers = ModifiersManager()

        self.objects = get_objects(context, lambda o: o.type == 'MESH')
        self.origin = None

        def apply(modifier:SimpleDeformModifier):
            modifier.angle = self.value
            modifier.factor = self.value
            modifier.deform_axis = self.axis
            modifier.deform_method = self.deform_method
            modifier.origin = self.origin
        def setup(modifier:SimpleDeformModifier):
            apply(modifier)
        self.modifiers.begin(self.objects)
        self.modifiers.modifier('SIMPLE_DEFORM', 'SimpleDeform', setup = setup, apply = apply)
        self.modifiers.end(search = self.existed)

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Value', 'Shift+Mouse', lambda: self.value)
        self.pane.prop('Axis', 'X/Y/Z', lambda: self.axis)
        self.pane.prop('Deform Method', 'Alt+Scroll', lambda: self.deform_method)
        self.pane.prop('Origin', 'E', lambda: None if self.origin is None else self.origin.name)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        self.modifiers.apply()
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        method = ('TWIST', 'BEND', 'TAPER', 'STRETCH')

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.value += (event.mouse_x - event.mouse_prev_x) / 100
                self.execute(context)
        elif event.type == 'X':
            self.axis = 'X'
            self.execute(context)
        elif event.type == 'Y':
            self.axis = 'Y'
            self.execute(context)
        elif event.type == 'Z':
            self.axis = 'Z'
            self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and event.alt:
            index = method.index(self.deform_method)
            self.deform_method = method[(index - 1) % len(method)]
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.alt:
            index = method.index(self.deform_method)
            self.deform_method = method[(index + 1) % len(method)]
            self.execute(context)
            self.execute(context)
        elif event.type == 'E' and event.value == 'PRESS':
            self.origin = eyedropper(
                context, event.mouse_region_x, event.mouse_region_y, self.objects
            )
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            self.modifiers.undo()
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class EdgeSplitModifier(Operator):
    bl_idname = 'nextmd.edge_split'
    bl_label = 'Edge Split Modifier'
    bl_options = {'REGISTER', 'UNDO'}

    existed: BoolProperty(default = False)

    angle: FloatProperty(default = radians(30))
    use_edge_angle: BoolProperty(default = True)
    use_edge_sharp: BoolProperty(default = True)

    @classmethod
    def poll(cls, context:Context):
        objects = get_objects(context, lambda o: o.type == 'MESH')
        if not objects: return False
        return True

    def draw(self, context:Context):
        layout = self.layout
        layout.prop(self, 'angle', text = 'Angle')
        layout.prop(self, 'use_edge_angle', text = 'Edge Angle')
        layout.prop(self, 'use_edge_sharp', text = 'Sharp Edges')

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)
        self.modifiers = ModifiersManager()

        self.objects = get_objects(context, lambda o: o.type == 'MESH')

        def apply(modifier:EdgeSplitModifier):
            modifier.split_angle = self.angle
            modifier.use_edge_angle = self.use_edge_angle
            modifier.use_edge_sharp = self.use_edge_sharp
        def setup(modifier:EdgeSplitModifier):
            apply(modifier)
        self.modifiers.begin(self.objects)
        self.modifiers.modifier('EDGE_SPLIT', 'EdgeSplit', setup = setup, apply = apply)
        self.modifiers.end(search = self.existed)

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Angle', 'Shift+Mouse', lambda: degrees(self.angle))
        self.pane.prop('Edge Angle', 'R', lambda: self.use_edge_angle)
        self.pane.prop('Sharp Edges', 'F', lambda: self.use_edge_sharp)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        self.modifiers.apply()
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
            if event.shift:
                self.angle += (event.mouse_x - event.mouse_prev_x) / 200
                self.execute(context)
        elif event.type == 'R' and event.value == 'PRESS':
            self.use_edge_angle = not self.use_edge_angle
            self.execute(context)
        elif event.type == 'F' and event.value == 'PRESS':
            self.use_edge_sharp = not self.use_edge_sharp
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            self.modifiers.undo()
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class ScrollModifiersEnableTool(Operator):
    bl_idname = 'nextmd.scroll_modifiers_enable'
    bl_label = 'Scroll Modifiers'
    bl_options = {'REGISTER', 'UNDO'}

    existed: BoolProperty(default = False)

    @classmethod
    def poll(cls, context:Context):
        objects = get_objects(context, lambda o: o.type == 'MESH')
        if not objects: return False
        return True

    def draw(self, context:Context):
        pass

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.index = 0
        self.objects = get_objects(context, lambda o: o.type == 'MESH')
        self.activity = list(itertools.chain.from_iterable(
            [(m, m.show_viewport, m.show_render) for m in o.modifiers] for o in self.objects
        ))
        self.count = max(len(o.modifiers) for o in self.objects)

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Count', 'Ctrl+Scroll', lambda: self.index)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        self.index = max(min(self.index, self.count), 0)
        for obj in self.objects:
            for i, modifier in enumerate(obj.modifiers):
                enable = i < self.index
                if modifier.show_viewport != enable: modifier.show_viewport = enable
                if modifier.show_render != enable: modifier.show_render = enable
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
        elif event.type == 'WHEELUPMOUSE' and event.ctrl:
            self.index += 1
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl:
            self.index -= 1
            self.execute(context)

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            for modifier, show_viewport, show_render in self.activity:
                modifier.show_viewport = show_viewport
                modifier.show_render = show_render
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class SortModifiersTool(Operator):
    bl_idname = 'nextmd.sort_modifiers'
    bl_label = 'Sort Modifiers'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        objects = get_objects(context, lambda o: o.type == 'MESH')
        if not objects: return False
        return True

    def draw(self, context:Context):
        pass
    
    def execute(self, context:Context):
        active = context.view_layer.objects.active
        objects = get_objects(context, lambda o: o.type == 'MESH')
        for obj in objects:
            straight_angle_bevel = [m for m in obj.modifiers if m.type == 'BEVEL' and m.profile >= 0.95]
            # TODO Проверить работоспособность
            subsurf = next((m for m in reversed(obj.modifiers) if m.type == 'SUBSURF' and m.subdivision_type == 'CATMULL_CLARK'), None)
            weighted_normal = [m for m in obj.modifiers if m.type == 'WEIGHTED_NORMAL']
            
            for m in straight_angle_bevel: bubble_modifier(obj, m)
            if straight_angle_bevel and subsurf is not None: bubble_modifier(obj, subsurf)
            for m in weighted_normal: bubble_modifier(obj, m)
            
            context.view_layer.objects.active = obj
            if not isclose(obj.scale.x, 1, abs_tol = 0.01) or \
                not isclose(obj.scale.y, 1, abs_tol = 0.01) or \
                not isclose(obj.scale.z, 1, abs_tol = 0.01):
                bpy.ops.object.transform_apply(location = False, rotation = False, scale = True)
            if weighted_normal: obj.data.use_auto_smooth = True
        context.view_layer.objects.active = active
        return {'FINISHED'}


class MoveModifiersTool(Operator):
    bl_idname = 'nextmd.move_modifiers'
    bl_label = 'Move Modifiers'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        if not context.active_object.select_get(): return False
        if not context.active_object.modifiers: return False
        return True

    def draw(self, context:Context):
        pass

    def invoke(self, context:Context, event:Event):
        self.pane = AdjustPane(Style.active)

        self.index = 0
        self.selected = None
        self.count = len(context.active_object.modifiers)
        self.activity = [(m.name, m.show_viewport, m.show_render) for m in context.active_object.modifiers]

        self.pane.begin()
        self.pane.header(self.bl_label)
        self.pane.prop('Select / Move', 'Ctrl+Scroll / Alt+Scroll', lambda: context.active_object.modifiers[self.index].name)
        self.pane.prop('Enable', 'F', lambda: context.active_object.modifiers[self.index].show_viewport)
        self.pane.move(dy = 10)
        add = lambda i: self.pane.status(
            text = lambda: context.active_object.modifiers[i].name,
            enable = lambda: context.active_object.modifiers[i].show_viewport,
            selected = lambda: i == self.index
        )
        for i, modifier in enumerate(context.active_object.modifiers): add(i)
        self.pane.end()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context:Context):
        self.index = max(min(self.index, self.count - 1), 0)
        if self.selected is None: return {'FINISHED'}
        # Moving modifier
        pos = next(i for i, m in enumerate(context.active_object.modifiers) if m.name == self.selected)
        while pos != self.index:
            if pos > self.index:
                bpy.ops.object.modifier_move_up(modifier = self.selected)
                pos -= 1
            else:
                bpy.ops.object.modifier_move_down(modifier = self.selected)
                pos += 1
        return {'FINISHED'}

    def modal(self, context:Context, event:Event):
        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.pane.x = event.mouse_region_x
            self.pane.y = event.mouse_region_y
        elif event.type == 'WHEELUPMOUSE' and event.ctrl and not event.alt:
            self.index -= 1
            self.selected = None
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and event.ctrl and not event.alt:
            self.index += 1
            self.selected = None
            self.execute(context)
        elif event.type == 'WHEELUPMOUSE' and not event.ctrl and event.alt:
            self.selected = context.active_object.modifiers[self.index].name
            self.index -= 1
            self.execute(context)
        elif event.type == 'WHEELDOWNMOUSE' and not event.ctrl and event.alt:
            self.selected = context.active_object.modifiers[self.index].name
            self.index += 1
            self.execute(context)
        elif event.type == 'F' and event.value == 'PRESS':
            context.active_object.modifiers[self.index].show_viewport = not context.active_object.modifiers[self.index].show_viewport
            context.active_object.modifiers[self.index].show_render = context.active_object.modifiers[self.index].show_viewport

        elif event.type == 'LEFTMOUSE':
            self.pane.remove()
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.pane.remove()
            # Restore order / sort
            for i, (name, show_viewport, show_render) in enumerate(self.activity):
                while context.active_object.modifiers[i].name != name:
                    bpy.ops.object.modifier_move_up(modifier = name)
                context.active_object.modifiers[i].show_viewport = show_viewport
                context.active_object.modifiers[i].show_render = show_render
            return {'CANCELLED'}
        
        if event.value == 'RELEASE':
            self.pane.flush()

        return {'RUNNING_MODAL'}


class OrientObjectsTool(Operator):
    bl_idname = 'nextmd.orient_objects'
    bl_label = 'Orient Objects'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context:Context):
        if context.active_object is None: return False
        if not context.active_object.select_get(): return False
        objects = get_objects(context, lambda o: o is not context.active_object)
        if not objects: return False
        return True

    def draw(self, context:Context):
        pass
    
    def execute(self, context:Context):
        objects = get_objects(context, lambda o: o is not context.active_object)
        location, rotation, scale = context.active_object.matrix_world.decompose()
        for obj in objects:
            l, r, s = obj.matrix_world.decompose()
            obj.matrix_world = Matrix.Translation(l) @ rotation.to_matrix().to_4x4() @ Matrix.Scale(1, 4, s)
        return {'FINISHED'}



class View3DPieMenu(Menu):
    bl_idname = "OBJECT_MT_view3d_pie"
    bl_label = "View 3D Pie"

    def draw(self, context:Context):
        layout = self.layout
        pie = layout.menu_pie()
        
        modifiers = pie.column()
        modifiers.label(text = 'Modifiers')

        arrays = modifiers.row(align = True)
        arrays.operator(LinearArrayModifier.bl_idname, text = '', icon = 'mod_array'.upper()) # Linear
        arrays.operator(CurveArrayModifier.bl_idname, text = '', icon = 'OUTLINER_DATA_CURVE') # Curve
        arrays.operator(RadialArrayModifier.bl_idname, text = '', icon = 'mesh_circle'.upper()) # Radial
        
        edges = modifiers.row(align = True)
        edges.operator(SmoothSharp.bl_idname, text = '', icon = 'SMOOTHCURVE') # Smooth Sharp
        edges.operator(CreaseSharpTool.bl_idname, text = '', icon = 'SHARPCURVE') # Crease Sharp
        edges.operator(BevelModifier.bl_idname, text = '', icon = 'MOD_BEVEL') # Bevel

        geometry = modifiers.column(align = True)
        # geometry.label(text = 'Geometry')
        geometry.operator(MirrorModifier.bl_idname, text = 'Mirror', icon = 'MOD_MIRROR')
        geometry.operator(SolidifyModifier.bl_idname, text = 'Solidify', icon = 'MOD_SOLIDIFY')
        geometry.operator(SubSurfModifier.bl_idname, text = 'Sub Surf', icon = 'MOD_SUBSURF')
        geometry.operator(BooleanModifier.bl_idname, text = 'Boolean', icon = 'MOD_BOOLEAN')
        geometry.operator(DisplaceModifier.bl_idname, text = 'Displace', icon = 'MOD_DISPLACE')
        geometry.operator(CurveModifier.bl_idname, text = 'Curve', icon = 'MOD_CURVE')
        geometry.operator(ScrewModifier.bl_idname, text = 'Screw', icon = 'MOD_SCREW')
        geometry.operator(SimpleDeformModifier.bl_idname, text = 'Simple Deform', icon = 'MOD_SIMPLEDEFORM')

        tools = pie.column(align = True)
        tools.label(text = 'Tool')
        tools.operator(WeightedNormalModifier.bl_idname, text = 'Weighted Normals')
        tools.operator(ApplyModifiersTool.bl_idname, text = 'Apply Modifiers')
        tools.operator(AlignViewportTool.bl_idname, text = 'Align Viewport')
        tools.operator(ScrollModifiersEnableTool.bl_idname, text = 'Scroll Modifiers')
        tools.operator(OrientObjectsTool.bl_idname, text = 'Orient Objects')

        pie.operator(SortModifiersTool.bl_idname)
        pie.operator(MoveModifiersTool.bl_idname)


classes = (
    # Modifiers
    LinearArrayModifier,
    CurveArrayModifier,
    RadialArrayModifier,
    MirrorModifier,
    DisplaceModifier,
    BooleanModifier,
    SmoothSharp,
    BevelModifier,
    SolidifyModifier,
    SubSurfModifier,
    WeightedNormalModifier,
    CurveModifier,
    ScrewModifier,
    SimpleDeformModifier,
    EdgeSplitModifier,

    # Tools
    AlignViewportTool,
    ApplyModifiersTool,
    CreaseSharpTool,
    ScrollModifiersEnableTool,
    SortModifiersTool,
    MoveModifiersTool,
    OrientObjectsTool,

    # Pie menus
    View3DPieMenu
)





addon_keymaps = []
def register():
    for cls in classes: bpy.utils.register_class(cls)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    km = wm.keyconfigs.addon.keymaps.new(name = '3D View', space_type = 'VIEW_3D')
    
    kmi = km.keymap_items.new('wm.call_menu_pie', 'W', 'PRESS', ctrl = True, shift = False, alt = False)
    kmi.properties.name =  View3DPieMenu.bl_idname
    
    addon_keymaps.append((km, kmi))

def unregister():
    for cls in classes: bpy.utils.unregister_class(reversed(cls))
    for km, kmi in addon_keymaps: km.keymap_items.remove(kmi)
    addon_keymaps.clear()

# if __name__ == '__main__':
register()