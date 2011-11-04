import bpy
from hashlib import sha1
from mathutils import Matrix, Vector

from bpy_extras.image_utils import load_image

from collada import Collada
from collada.triangleset import TriangleSet
from collada.material import Map

def load(op, ctx, filepath=None, **kwargs):
    import os
    
    c = Collada(filepath)
    
    imp = ColladaImport(ctx, c, os.path.dirname(filepath))

    for obj in c.scene.objects('geometry'):
        imp.import_geometry(obj)

    return {'FINISHED'}


class ColladaImport(object):
    def __init__(self, ctx, collada, basedir):
        self._ctx = ctx
        self._collada = collada
        self._basedir = basedir
        self._imported_geometries = []
        self._images = {}
        
    def import_geometry(self, bgeom):
        b_materials = {}
        for sym, matnode in bgeom.materialnodebysymbol.items():
            mat = matnode.target
            b_matname = self.import_name(mat)
            if b_matname not in bpy.data.materials:
                self.import_material(mat, b_matname)
            b_materials[sym] = bpy.data.materials[b_matname]

        for i, p in enumerate(bgeom.original.primitives):
            b_obj = None
            b_meshname = self.import_name(bgeom.original, i)
            if isinstance(p, TriangleSet):
                b_obj = self.import_geometry_triangleset(p, b_meshname, b_materials[p.material])
            else:
                continue
            if not b_obj:
                continue

            self._ctx.scene.objects.link(b_obj)
            self._ctx.scene.objects.active = b_obj
            b_obj.matrix_world = _transposed(bgeom.matrix)
            bpy.ops.object.material_slot_add()
            b_obj.material_slots[0].material = b_materials[p.material]

    def import_geometry_triangleset(self, triset, b_name, b_mat):
        b_mesh = None
        if b_name in bpy.data.meshes:
            b_mesh = bpy.data.meshes[b_name]
        else:
            if triset.vertex_index is None or \
                    not len(triset.vertex_index):
                return

            b_mesh = bpy.data.meshes.new(b_name)
            b_mesh.vertices.add(len(triset.vertex))
            b_mesh.faces.add(len(triset.vertex_index))
            for vidx, vertex in enumerate(triset.vertex):
                b_mesh.vertices[vidx].co = vertex

            # eekadoodle
            eekadoodle_faces = []
            for v1, v2, v3 in triset.vertex_index:
                eekadoodle_faces.extend([v3, v1, v2, 0] if v3 == 0 else [v1, v2, v3, 0])
            b_mesh.faces.foreach_set("vertices_raw", eekadoodle_faces)
            
            has_normal = (triset.normal_index is not None)
            has_uv = (len(triset.texcoord_indexset) > 0)
            
            if has_normal or has_uv:
                if has_uv:
                    b_mesh.uv_textures.new()
                for i, f in enumerate(b_mesh.faces):
                    if has_normal:
                        f.use_smooth = not _is_flat_face(
                                triset.normal[triset.normal_index[i]])
                    if has_uv:
                        t1, t2, t3 = triset.texcoord_indexset[0][i]
                        tface = b_mesh.uv_textures[0].data[i]
                        # eekadoodle
                        if triset.vertex_index[i][2] == 0:
                            t1, t2, t3 = t3, t1, t2
                        tface.uv1 = triset.texcoordset[0][t1]
                        tface.uv2 = triset.texcoordset[0][t2]
                        tface.uv3 = triset.texcoordset[0][t3]
                        if b_mat.name in self._images:
                            tface.image = self._images[b_mat.name]
                        
            b_mesh.update()

        b_obj = bpy.data.objects.new(b_name, b_mesh)
        b_obj.data = b_mesh
        return b_obj

    def import_material(self, mat, b_name):
        b_mat = bpy.data.materials.new(b_name)
        b_mat.diffuse_shader = 'LAMBERT'
        getattr(self, 'import_rendering_' + \
                mat.effect.shadingtype)(mat, b_mat)

    def import_rendering_blinn(self, mat, b_mat):
        effect = mat.effect
        self.import_rendering_diffuse(effect.diffuse, b_mat)

    def import_rendering_constant(self, mat, b_mat):
        effect = mat.effect

    def import_rendering_lambert(self, mat, b_mat):
        effect = mat.effect
        self.import_rendering_diffuse(effect.diffuse, b_mat)

    def import_rendering_phong(self, mat, b_mat):
        effect = mat.effect
        self.import_rendering_diffuse(effect.diffuse, b_mat)

    def import_rendering_diffuse(self, diffuse, b_mat):
        if isinstance(diffuse, Map):
            image_path = diffuse.sampler.surface.image.path
            image = load_image(image_path, self._basedir)
            if image is not None:
                texture = bpy.data.textures.new(name='Kd', type='IMAGE')
                texture.image = image
                mtex = b_mat.texture_slots.add()
                mtex.texture_coords = 'UV'
                mtex.texture = texture
                mtex.use_map_color_diffuse = True
                self._images[b_mat.name] = image
            else:
                b_mat.diffuse_color = 1., 0., 0.
        elif isinstance(diffuse, tuple):
            b_mat.diffuse_color = diffuse[:3]
                
    def import_name(self, obj, index=0):
        base = ('%s-%d' % (obj.id, index))
        return base[:10] + sha1(base.encode('utf-8')
                ).hexdigest()[:10]


def _is_flat_face(normal):
    a = Vector(normal[0])
    for n in normal[1:]:
        dp = a.dot(Vector(n))
        if dp < 0.99999 or dp > 1.00001:
            return False
    return True

def _transposed(matrix):
    m = Matrix(matrix)
    m.transpose()
    return m

