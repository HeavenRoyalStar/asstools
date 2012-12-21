# Inter-Quake Import
#
# Simple version that only imports positions, normals and texture coords.
# Armatures, vertex colors, custom attributes are all ignored.
#

bl_info = {
	"name": "Import Inter-Quake Export Simple (.iqe)",
	"description": "Import Inter-Quake Export Simple.",
	"author": "Tor Andersson",
	"version": (2012, 12, 18),
	"blender": (2, 6, 5),
	"location": "File > Import > Inter-Quake Model",
	"wiki_url": "http://github.com/ccxvii/asstools",
	"category": "Import-Export",
}

import bpy, bmesh, shlex, os, sys, glob

from bpy.props import *
from bpy_extras.io_utils import ImportHelper, unpack_list, unpack_face_list
from bpy_extras.image_utils import load_image

def reorder(f, ft):
	# see bpy_extras.io_utils.unpack_face_list()
	if len(f) == 3:
		if f[2] == 0:
			f = f[1], f[2], f[0]
			ft = ft[1], ft[2], ft[0]
	else: # assume quad
		if f[3] == 0 or f[2] == 0:
			f = f[2], f[3], f[0], f[1]
			ft = ft[2], ft[3], ft[0], ft[1]
	return f, ft

def import_material_cycles(matname, dirname):
	texname = matname
	imgname = texname + ".png"

	if imgname in bpy.data.images:
		img = bpy.data.images[imgname]
	else:
		img = load_image("textures/" + imgname, dirname, place_holder=True)

	if matname in bpy.data.materials:
		mat = bpy.data.materials[matname]
	else:
		mat = bpy.data.materials.new(matname)
		mat.use_nodes = True
		nodes = mat.node_tree.nodes
		links = mat.node_tree.links
		n_img = nodes.new('TEX_IMAGE')
		n_img.image = img
		n_img.show_texture = True
		n_mix = nodes.new('MIX_SHADER')
		n_tran = nodes.new('BSDF_TRANSPARENT')
		n_diff = nodes.new('BSDF_DIFFUSE')
		n_out = nodes.new('OUTPUT_MATERIAL')
		links.new(n_img.outputs['Color'], n_diff.inputs['Color'])
		links.new(n_img.outputs['Alpha'], n_mix.inputs[0])
		links.new(n_tran.outputs['BSDF'], n_mix.inputs[1])
		links.new(n_diff.outputs['BSDF'], n_mix.inputs[2])
		links.new(n_mix.outputs[0], n_out.inputs['Surface'])

	return mat, img

def import_material(matname, dirname):
	texname = matname
	imgname = texname + ".png"

	if imgname in bpy.data.images:
		img = bpy.data.images[imgname]
	else:
		img = load_image("textures/" + imgname, dirname, place_holder=True)
		# img.use_premultiply = True -- True for BI, false for GLSL

	if texname in bpy.data.textures:
		tex = bpy.data.textures[texname]
	else:
		tex = bpy.data.textures.new(texname, type='IMAGE')
		tex.image = img
		tex.use_alpha = True

	if matname in bpy.data.materials:
		mat = bpy.data.materials[matname]
	else:
		mat = bpy.data.materials.new(matname)
		mat.game_settings.alpha_blend = 'CLIP'
		mat.diffuse_intensity = 1.0
		mat.specular_intensity = 0.0
		mat.use_transparency = True
		mat.alpha = 0.0
		slot = mat.texture_slots.create(0)
		slot.texture = tex
		slot.texture_coords = 'UV'
		slot.uv_layer = "UVMap"
		slot.use_map_color_diffuse = True
		slot.use_map_alpha = True

	return mat, img

def isdegenerate(f):
	if len(f) == 3:
		a, b, c = f
		return a == b or a == c or b == c
	if len(f) == 4:
		a, b, c, d = f
		return a == b or a == c or a == d or b == c or b == d
	return True

def import_mesh(filename):
	print("importing", filename)

	name = filename.split("/")[-1].split("\\")[-1].split(".")[0]
	file = open(filename)
	line = file.readline()
	if not line.startswith("# Inter-Quake Export"):
		raise Exception("Not an IQE file!")

	faces = []
	mat, img = None, None
	for line in file.readlines():
		if "#" in line or "\"" in line:
			line = shlex.split(line, "#")
		else:
			line = line.split()
		if len(line) == 0: pass
		elif line[0] == "mesh": in_vp, in_vn, in_vt = [], [], []
		elif line[0] == "material": mat, img = import_material_cycles(line[1], os.path.dirname(filename))
		elif line[0] == "vp": in_vp.append((float(line[1]), float(line[2]), float(line[3])))
		elif line[0] == "vn": in_vn.append((float(line[1]), float(line[2]), float(line[3])))
		elif line[0] == "vt": in_vt.append((float(line[1]), 1.0 - float(line[2])))
		elif line[0] == "fm":
			verts = []
			for f in [int(x) for x in line[1:]]:
				verts.insert(0, (in_vp[f], in_vn[f], in_vt[f]))
			faces.append((verts, mat, img))

	vertex_map = {}
	out_vp, out_f, out_ft, out_fm = [], [], [], []
	for verts, mat, img in faces:
		f, ft = [], []
		for p, n, t in verts:
			if not (p,n) in vertex_map:
				vertex_map[(p,n)] = len(out_vp)
				out_vp.append(p)
			f.append(vertex_map[p,n])
			ft.append(t)
		f, ft = reorder(f, ft)
		if isdegenerate(f):
			print("degenerate face", f)
			continue
		out_f.append(f)
		out_ft.append(ft)
		out_fm.append((mat, img))

	mesh = bpy.data.meshes.new(name)
	obj = bpy.data.objects.new(name, mesh)
	grp = bpy.data.groups.new(name)
	grp.objects.link(obj)

	mesh.show_double_sided = False

	mesh.vertices.add(len(out_vp))
	mesh.vertices.foreach_set("co", unpack_list(out_vp))
	mesh.tessfaces.add(len(out_f))
	mesh.tessfaces.foreach_set("vertices_raw", unpack_face_list(out_f))

	uvlayer = mesh.tessface_uv_textures.new()
	for i, face in enumerate(mesh.tessfaces):
		mat, img = out_fm[i]
		if mat.name not in mesh.materials:
			mesh.materials.append(mat)
		face.material_index = mesh.materials.find(mat.name)
		face.use_smooth = True
		uvlayer.data[i].image = img
		uvlayer.data[i].uv1 = out_ft[i][0]
		uvlayer.data[i].uv2 = out_ft[i][1]
		uvlayer.data[i].uv3 = out_ft[i][2]
		uvlayer.data[i].uv4 = out_ft[i][3] if len(out_ft[i]) == 4 else (0,0)

	mesh.update()

	bpy.context.scene.objects.link(obj)
	bpy.context.scene.objects.active = obj

#
# Register addon
#

class ImportIQESimple(bpy.types.Operator, ImportHelper):
	bl_idname = "import.iqm"
	bl_label = "Import IQE Simple"

	filename_ext = ".iqe"
	filter_glob = StringProperty(default="*.iqe", options={'HIDDEN'})
	filepath = StringProperty(name="File Path", maxlen=1024, default="")

	def execute(self, context):
		import_iqm(self.properties.filepath, self.bone_axis)
		return {'FINISHED'}

def menu_func(self, context):
	self.layout.operator(ImportIQESimple.bl_idname, text="Inter-Quake Export Simple (.iqe)")

def register():
	bpy.utils.register_module(__name__)
	bpy.types.INFO_MT_file_import.append(menu_func)

def unregister():
	bpy.utils.unregister_module(__name__)
	bpy.types.INFO_MT_file_import.remove(menu_func)

def batch_zap():
	if "Cube" in bpy.data.objects:
		obj = bpy.data.objects['Cube']
		bpy.context.scene.objects.unlink(obj)
		bpy.data.objects.remove(obj)

def batch(input):
	batch_zap()
	output = os.path.splitext(input)[0] + ".blend"
	import_mesh(input)
	print("Saving", output)
	bpy.ops.wm.save_mainfile(filepath=output, check_existing=False)

def batch_many(input_list):
	batch_zap()
	output = "output.blend"
	for input in input_list:
		import_mesh(input)
	print("Saving", output)
	bpy.ops.wm.save_mainfile(filepath=output, check_existing=False)

if __name__ == "__main__":
	register()
	if len(sys.argv) > 4 and sys.argv[-2] == '--':
		if "*" in sys.argv[-1]:
			batch_many(glob.glob(sys.argv[-1]))
		else:
			batch(sys.argv[-1])
	elif len(sys.argv) > 4 and sys.argv[4] == '--':
		batch_many(sys.argv[5:])
