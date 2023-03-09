class StereoCategory:
	def __init__(self, id: str, name: str, code: str, version: str) -> None:
		self.id = id
		self.name = name
		self.code = code
		self.version = version

	def get_id(self) -> int:
		return self.id

	def get_name(self) -> str:
		return self.name

	def get_code(self) -> str:
		return self.code

	def get_version(self) -> str:
		return self.version

	# Define as dict for json serialization
	def as_dict(self) -> dict:
		return {
			'id': self.id,
			'name': self.name,
			'code': self.code,
			'version': self.version
		}

	def __str__(self) -> str:
		return "id: " + id + " , " + "name: " + name + " , " + "code: " + code + " , " + "version: " + version
