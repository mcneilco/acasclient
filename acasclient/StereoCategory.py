class StereoCategory:
	def __init__(self, id, name, code, version):
		self.id = id
		self.name = name
		self.code = code
		self.version = version

	def get_id(self):
		return self.id

	def get_name(self):
		return self.name

	def get_code(self):
		return self.code

	def get_version(self):
		return self.version

	# Define as dict for json serialization
	def as_dict(self):
		return {
			'id': self.id,
			'name': self.name,
			'code': self.code,
			'version': self.version
		}

	def __str__():
 		return "id: " + id + " , " + "name: " + name + " , " + "code: " + code + " , " + "version: " + version
