#!/usr/bin/env python

from glob import iglob
import shlex
from toposort import toposort_flatten
from os.path import basename, dirname
import sys
from getpass import getuser

buildspace = sys.argv[1] if len(sys.argv) > 1 else getuser()

images = {}

# Parse all our Dockerfiles
for fn in iglob("**/Dockerfile"):
	with open(fn, "r") as fp:
		data = {'fn': fn, 'basename': buildspace + "/" + basename(dirname(fn))}
		lines = fp.readlines()
		# Handle lines that end with a \
		parsed_lines = []
		for line in lines:
			if line.endswith("\\"):
				parsed_lines[-1] += "\n" + line.strip()
			else:
				parsed_lines.append(line.strip())
		for line in parsed_lines:
			if line.startswith("FROM "):
				data['parent'] = line[5:]
			if line.startswith("ENV "):
				# shlex to handle string escaping
				parts = shlex.split(line[4:])
				i = iter(parts)
				vars = {}
				while True:
					try:
						part = next(i)
						if '=' in part:
							key, val = part.split('=', 1)
							vars[key.strip()] = val.strip()
						else:
							key = part
							val = next(i)
							vars[key.strip()] = val.strip()
					except StopIteration:
						break
				for var, val in vars.iteritems():
					if var.endswith("_VERSION"):
						data['version'] = val
						break
		if not data['parent']:
			print("Error: {} does not specify a parent".format(fn))
			continue
		if 'version' not in data and ':' in data['parent']:
			data['version'] = data['parent'].split(':', 1)[1]
		if 'version' not in data:
			data['version'] = "latest"
		data['name'] = data['basename'] + ':' + data['version']
	if data['name'] in images:
		print("Error: {} has duplicate Dockerfiles".format(data['name']))
		sys.exit(0)
	images[data['name']] = data

# Build up our dependency list
deps = {}
for k in images.keys():
	data = images[k]
	image_name = data['name']
	image_deps = set()
	if data['parent'].startswith(buildspace + "/"):
		if data['parent'].endswith(":latest") or not ':' in data['parent']:
			# Depend on all images with the same prefix
			search_key = data['parent'][:-7] if ':' in data['parent'] else data['parent']
			for check in images.keys():
				if check == search_key or check.startswith(search_key + ":"):
					image_deps.add(check)
		else:
			# Sanity check - if the parent is out-of-tree, no point trying to find it
			if data['parent'] in images.keys():
				image_deps.add(data['parent'])
	deps[image_name] = image_deps

for image in toposort_flatten(deps):
	data = images[image]
	print("{}\t{}\t{}".format(dirname(data['fn']), data['basename'], data['version']))