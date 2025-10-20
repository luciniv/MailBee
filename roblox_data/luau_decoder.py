import re
import math


class BrickColor:
    def __init__(self, number):
        self.Number = number

    def __str__(self):
        return f"BrickColor({self.Number})"


class Ray:
    def __init__(self, origin, direction):
        self.Origin = origin
        self.Direction = direction

    def __str__(self):
        return f"Ray({self.Origin}, {self.Direction})"


class CFrame:
    def __init__(self, *components):
        self._components = components

    def components(self):
        return self._components

    def __str__(self):
        return f"CFrame{self._components}"


class Vector3:
    def __init__(self, X, Y, Z):
        self.X = X
        self.Y = Y
        self.Z = Z

    def __str__(self):
        return f"Vector3({self.X}, {self.Y}, {self.Z})"


class Color3:
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

    def __str__(self):
        return f"Color3({self.r}, {self.g}, {self.b})"


EFormat = {
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
    '"': '\\"',
    "\\": "\\\\",
}
DFormat = {v: k for k, v in EFormat.items()}


def safe_string(s, enc_str):
    if enc_str:
        return re.sub(r'[\x08\t\n\f\r"\\]', lambda m: EFormat[m.group(0)], s)
    else:
        return re.sub(r"\\.", lambda m: DFormat.get(m.group(0), m.group(0)), s)


def round_number(number, precision=None):
    places = 10**precision if precision is not None else 1
    return math.floor(number * places + 0.5) / places


def extract(data):
    if re.match(r"^\[.*?\]$", data):
        return JSON.decode(data)
    m = re.match(r'^"(.*?)"$', data)
    if m:
        return safe_string(m.group(1), False)
    if re.match(r"^true$", data):
        return True
    if re.match(r"^false$", data):
        return False
    m = re.match(r"^B\[(\d+)\]$", data)
    if m:
        return str(BrickColor(int(m.group(1))))
    m = re.match(r"^R\[(.+)\]$", data)
    if m:
        m2 = re.match(r"(.+),(.+),(.+),(.+),(.+),(.+)", m.group(1))
        if m2:
            A, B, C, X, Y, Z = m2.groups()
            return str(
                Ray(
                    Vector3(float(A), float(B), float(C)),
                    Vector3(float(X), float(Y), float(Z)),
                )
            )
    m = re.match(r"^CF\[(.+)\]$", data)
    if m:
        m2 = re.match(
            r"(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+)", m.group(1)
        )
        if m2:
            parts = [float(x) for x in m2.groups()]
            return str(CFrame(*parts))
    m = re.match(r"^V3\[(.+)\]$", data)
    if m:
        m2 = re.match(r"(.+),(.+),(.+)", m.group(1))
        if m2:
            A, B, C = m2.groups()
            return str(Vector3(float(A), float(B), float(C)))
    m = re.match(r"^C3\[(.+)\]$", data)
    if m:
        m2 = re.match(r"(.+),(.+),(.+)", m.group(1))
        if m2:
            A, B, C = m2.groups()
            return str(Color3(float(A), float(B), float(C)))
    try:
        return float(data)
    except:
        return None


class JSON:
    @staticmethod
    def encode(table, buff=None):
        if buff is None:
            buff = {}
        result = []

        if isinstance(table, dict):
            items = table.items()
        elif isinstance(table, list):
            items = enumerate(table, 1)
        else:
            items = []

        for index, value in items:
            idx_str = ""
            val_str = "null"

            if isinstance(index, str):
                idx_str = '"' + safe_string(index, True) + '":'
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                val_str = str(value)
            elif isinstance(value, bool):
                val_str = "true" if value else "false"
            elif isinstance(value, str):
                val_str = '"' + safe_string(value, True) + '"'
            elif isinstance(value, (dict, list)):

                if id(value) not in buff:
                    buff[id(value)] = True
                    val_str = JSON.encode(value, buff)

            elif isinstance(value, BrickColor):
                val_str = "B[" + str(value.Number) + "]"
            elif isinstance(value, Ray):
                ori = value.Origin
                d = value.Direction
                val_str = (
                    "R["
                    + ",".join(str(x) for x in [ori.X, ori.Y, ori.Z, d.X, d.Y, d.Z])
                    + "]"
                )
            elif isinstance(value, CFrame):
                comps = value.components()
                val_str = "CF[" + ",".join(str(x) for x in comps) + "]"
            elif isinstance(value, Vector3):
                val_str = (
                    "V3[" + ",".join(str(x) for x in [value.X, value.Y, value.Z]) + "]"
                )
            elif isinstance(value, Color3):
                val_str = (
                    "C3["
                    + ",".join(
                        str(round_number(v, 3)) for v in (value.r, value.g, value.b)
                    )
                    + "]"
                )
            result.append(idx_str + val_str)
        return "[" + ";".join(result) + "]"

    @staticmethod
    def decode(s):
        result = []
        result_dict = {}
        tables = 0
        esc = False
        quo = False
        layer = None
        n = len(s)

        for idx in range(n):
            char = s[idx]

            if layer is not None:
                layer.append(char)
            elif layer is None and idx != 0:
                layer = [char]

            if not esc:
                if char == "\\":
                    esc = True
                elif char == '"':
                    quo = not quo
                elif ((not quo) and (char == ";") and (tables == 1)) or (idx == n - 1):

                    token = "".join(layer) if layer is not None else char
                    if re.match(r'^".*":.+$', token.replace('\\"', "")):
                        key_end = None

                        for j in range(1, len(token)):
                            if token[j] == '"':
                                key_end = j
                                break

                        if key_end is None:
                            key_end = 1

                        key_str = token[1:key_end]
                        value_token = token[key_end + 2 : -1]
                        result_dict[safe_string(key_str, False)] = extract(value_token)
                    else:
                        token_core = token[0:-1]
                        result.append(extract(token_core))
                    layer = None

                elif not quo:
                    if char == "[":
                        tables += 1
                    elif char == "]":
                        tables -= 1
            else:
                esc = False

        if result_dict:
            for i, v in enumerate(result, 1):
                result_dict[i] = v
            return result_dict
        else:
            return result
