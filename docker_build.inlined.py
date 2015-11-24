#!/usr/bin/env python

from glob import iglob
import shlex
from os.path import basename, dirname
import sys
from getpass import getuser

#######################################################################
# Implements a topological sort algorithm.
#
# Copyright 2014 True Blade Systems, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Notes:
#  Based on http://code.activestate.com/recipes/578272-topological-sort
#   with these major changes:
#    Added unittests.
#    Deleted doctests (maybe not the best idea in the world, but it cleans
#     up the docstring).
#    Moved functools import to the top of the file.
#    Changed assert to a ValueError.
#    Changed iter[items|keys] to [items|keys], for python 3
#     compatibility. I don't think it matters for python 2 these are
#     now lists instead of iterables.
#    Copy the input so as to leave it unmodified.
#    Renamed function from toposort2 to toposort.
#    Handle empty input.
#    Switch tests to use set literals.
#
########################################################################

from functools import reduce as _reduce

def toposort(data):
    """Dependencies are expressed as a dictionary whose keys are items
and whose values are a set of dependent items. Output is a list of
sets in topological order. The first set consists of items with no
dependences, each subsequent set consists of items that depend upon
items in the preceeding sets.
"""

    # Special case empty input.
    if len(data) == 0:
        return

    # Copy the input so as to leave it unmodified.
    data = data.copy()

    # Ignore self dependencies.
    for k, v in data.items():
        v.discard(k)
    # Find all items that don't depend on anything.
    extra_items_in_deps = _reduce(set.union, data.values()) - set(data.keys())
    # Add empty dependences where needed.
    data.update({item:set() for item in extra_items_in_deps})
    while True:
        ordered = set(item for item, dep in data.items() if len(dep) == 0)
        if not ordered:
            break
        yield ordered
        data = {item: (dep - ordered)
                for item, dep in data.items()
                    if item not in ordered}
    if len(data) != 0:
        raise ValueError('Cyclic dependencies exist among these items: {}'.format(', '.join(repr(x) for x in data.items())))


def toposort_flatten(data, sort=True):
    """Returns a single list of dependencies. For any set returned by
toposort(), those items are sorted and appended to the result (just to
make the results deterministic)."""

    result = []
    for d in toposort(data):
        result.extend((sorted if sort else list)(d))
    return result


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
