local JSON = {}

local Extract;

local SetMeta	= setmetatable;
local Tostring	= tostring;
local Tonumber	= tonumber;
local Concat	= table.concat;
local Gsub, Sub	= string.gsub, string.sub;
local Match		= string.match;
local Type		= typeof;

local roblox = require("@lune/roblox")
local C3, V3, CF, Ray, Bri	= roblox.Color3.new, roblox.Vector3.new, roblox.CFrame.new, roblox.Ray.new, roblox.BrickColor.new; -- Yell at me for this lengthy definition later.

local EFormat, DFormat	= {}, {};
local Backs = {
	{'\b', '\\b'};
	{'\t', '\\t'};
	{'\n', '\\n'};
	{'\f', '\\f'};
	{'\r', '\\r'};
	{'"', '\\"'};
	{'\\', '\\\\'};
};

for Idx = 1, #Backs do
	local Pair	= Backs[Idx];

	EFormat[Pair[1]]	= Pair[2];
	DFormat[Pair[2]]	= Pair[1];
end;

Backs	= nil;

local __tMemoize	= {
	__index	= function(self, String)
		local Res	= Match(self[1], String);

		self[2]	= Res;

		return Res;
	end;
};

local function SafeString(String, EncStr)
	if EncStr then
		return (Gsub(String, '[\b\t\n\f\r\\"]', EFormat));
	else
		return (Gsub(String, '\\.', DFormat));
	end;
end;

function Extract(Data)
	local Mem	= SetMeta({Data}, __tMemoize);

	if Mem['^%[.-%]$'] then -- Things are decoded here, feel free to add.
		return JSON:Decode(Mem[2]);
	elseif Mem['^"(.-)"$'] then
		return SafeString(Mem[2]);
	elseif Mem['^true$'] then
		return true;
	elseif Mem['^false$'] then
		return false;
	elseif (Mem['^B%[(%d+)%]$']) then
		return tostring(Bri(Mem[2]));
	elseif (Mem['^R%[(.+)%]$']) then
		local A, B, C, X, Y, Z	= Match(Mem[2], '(.+),(.+),(.+),(.+),(.+),(.+)');

		return tostring(Ray(V3(A, B, C), V3(X, Y, Z)));
	elseif (Mem['^CF%[(.+)%]$']) then
		return tostring(CF(Match(Mem[2], '(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+),(.+)')));
	elseif (Mem['^V3%[(.+)%]$']) then
		return tostring(V3(Match(Mem[2], '(.+),(.+),(.+)')));
	elseif (Mem['^C3%[(.+)%]$']) then
		return tostring(C3(Match(Mem[2], '(.+),(.+),(.+)')));
	else
		return Tonumber(Data);
	end;
end;

function Round(Number: number, Precision: number?) : number
	local Places = (Precision) and (10^Precision) or 1
	return (((Number * Places) + 0.5 - ((Number * Places) + 0.5) % 1)/Places)
end

function JSON:Encode(Table, Buff)
	local Result	= {};
	local Buff		= Buff or {};

	for Index, Value in next, Table do
		local Idx, Val	= '', 'null';
		local ValT		= Type(Value);

		if (Type(Index) == 'string') then
			Idx	= Concat{'"', SafeString(Index, true), '":'};
		end;

		if (ValT == 'number') or (ValT == 'boolean') then -- Things are encoded here; feel free to add.
			Val	= Tostring(Value);
		elseif (ValT == 'string') then
			Val	= Concat{'"', SafeString(Value, true), '"'};
		elseif (ValT == 'table') and (not Buff[Value]) then
			Buff[Value]	= true;

			Val	= JSON:Encode(Value, Buff);
		elseif (ValT == 'BrickColor') then
			Val	= Concat{'B[', Value.Number, ']'};
		elseif (ValT == 'Ray') then
			local Ori, Dir	= Value.Origin, Value.Direction;

			Val	= Concat{'R[', Concat({Ori.X, Ori.Y, Ori.Z, Dir.X, Dir.Y, Dir.Z}, ','), ']'};
		elseif (ValT == 'CFrame') then
			Val	= Concat{'CF[', Concat({Value:components()}, ','), ']'};
		elseif (ValT == 'Vector3') then
			Val	= Concat{'V3[', Concat({Value.X, Value.Y, Value.Z}, ','), ']'};
		elseif (ValT == 'Color3') then
			Val	= Concat{'C3[', Concat({Round(Value.r, 3), Round(Value.g, 3), Round(Value.b, 3)}, ','), ']'};
		end;

		Result[#Result + 1]	= (Idx .. Val);
	end;

	return Concat{'[', Concat(Result, ';'), ']'};
end;

function JSON:Decode(String)
	local Result	= {};
	local Tables	= 0;
	local Len		= #String;
	local Esc, Quo;
	local Layer;

	for Idx = 1, Len do
		local Char	= Sub(String, Idx, Idx);

		if Layer then
			Layer[#Layer + 1]	= Char;
		elseif (not Layer) and (Idx ~= 1) then
			Layer	= {Char};
		end;

		if (not Esc) then
			if (Char == '\\') then
				Esc	= true;
			elseif (Char == '"') then
				Quo	= (not Quo);
			elseif ((not Quo) and (Char == ';') and (Tables == 1)) or (Idx == Len) then
				local Lay	= Concat(Layer);
				local Index	= Match(Gsub(Lay, '\\"', ''), '^".-":.+$');

				if Index then
					Index	= false;

					for Idz = 2, #Layer do
						local Char	= Layer[Idz];

						if (not Index) then
							if (Char == '"') then
								Index	= Idz - 1;

								break;
							else
								Index	= (Char == '\\');
							end;
						else
							Index	= false;
						end;
					end;

					Result[SafeString(Sub(Lay, 2, Index))]	= Extract(Sub(Lay, Index + 3, -2));
				else
					Result[#Result + 1]	= Extract(Sub(Lay, 1, -2));
				end;

				Layer	= nil;
			elseif (not Quo) then
				if (Char == '[') then
					Tables	= Tables + 1;
				elseif (Char == ']') then
					Tables	= Tables - 1;
				end;
			end;
		else
			Esc	= false;
		end;
	end;

	return Result;
end;

return JSON