local JSON = require("JSON")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local process = require("@lune/process")

-- Get the input file name from the command-line arguments
local processArgs = table.clone(process.args)
local input_file = processArgs[1]

-- Read the input string from the file
local text = fs.readFile(input_file)
if not text then
    error("Failed to read input file.")
end

-- Process the input string
text = text:sub(2, -2)
text = text:gsub("\\\"", "\"")
text = text:gsub("[\128-\255]", "")

-- Decode JSON and re-encode it using serde
local tbl = JSON:Decode(text)
local new_data = serde.encode("json", tbl, true)

-- Output the result
print(new_data)