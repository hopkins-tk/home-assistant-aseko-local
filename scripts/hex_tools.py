from operator import index

from numpy import byte


def print_hex_table(data: bytes) -> None:
    """Prints a table of byte index and hex value."""
    print("Byte Nr | HEX")
    print("--------|-----")
    for i, b in enumerate(data):
        print(f"{i:03d}     | {b:02x}")


def print_hex_table_full(data: bytes) -> None:
    """Prints a table of byte index and hex value."""
    print("Byte Nr | HEX  | Dec Byte | Dec Word")
    print("--------|-----")
    for i, b in enumerate(data):
        print(
            f"{i:03d}     | {b:02x}  | {b:3d}     | {int.from_bytes(data[i : i + 2], 'big') if i + 1 < len(data) else 'N/A':6}"
        )


def write_hex_table_md(data: bytes, filename: str) -> None:
    """Writes the hex table to a markdown file."""
    with open(filename, "w") as f:
        f.write("| Byte Nr | HEX | Dec Byte | Dec Word |\n")
        f.write("|---------|-----|----------|----------|\n")
        for i, b in enumerate(data):
            if i + 1 < len(data):
                word = f"{int.from_bytes(data[i : i + 2], 'big'):6}"
            else:
                word = "N/A"
            f.write(f"| {i:03d} | {b:02x} | {b:3d} | {word} |\n")


def print_byte_info(data: bytes, byte_index: int) -> None:
    """Prints the hex value and big-endian integer value for a given byte index and length."""
    byte_value = data[byte_index:byte_index].hex()
    word_value = int.from_bytes(data[byte_index : byte_index + 2], "big")
    print(f"byte value = 0x{byte_value} / word value: {word_value})")


def generate_bytearray(data: bytes) -> None:
    """
    Generates a Python function that fills a bytearray with values from a hexstring,
    using a mapping of byte positions and names.
    byte_map: List of dicts with keys: 'name', 'start', 'end', 'type'
    type: 'byte' or 'word'
    """

    byte_map = [
        {"name": "serial_number", "byte": "0:3", "comment": ""},
        {"name": "probe info", "byte": "4", "comment": ""},
        {"name": "year", "byte": "6", "comment": "eg 25 (2000+year), NET = FF always"},
        {"name": "month", "byte": "7", "comment": ""},
        {"name": "day", "byte": "8", "comment": ""},
        {"name": "hour", "byte": "9", "comment": ""},
        {"name": "minute", "byte": "10", "comment": ""},
        {"name": "second", "byte": "11", "comment": ""},
        {"name": "ph_value", "byte": "14:15", "comment": ""},
        {"name": "cl_free or redox", "byte": "16:17", "comment": ""},
        {
            "name": "redox",
            "byte": "18:19",
            "comment": "Aqua Pro only clf and redox probes",
        },
        {"name": "salinity", "byte": "20", "comment": "Aqua Salt only"},
        {"name": "electrolyzer_power", "byte": "21", "comment": "Aqua Salt only"},
        {
            "name": "cl_free_mv",
            "byte": "20:21",
            "comment": "Aqua Net if clf probe, others?",
        },
        {"name": "water_temperature", "byte": "25:26", "comment": ""},
        {"name": "water_flow_probe", "byte": "28", "comment": ""},
        {"name": "pump_or_electrolizer", "byte": "29", "comment": ""},
        {"name": "required_ph", "byte": "52", "comment": ""},
        {
            "name": "required_cl_free_or_redox",
            "byte": "53",
            "comment": "if clf and redox probe then required clf",
        },
        {"name": "required_algicide", "byte": "54", "comment": ""},
        {"name": "required_water_temperature", "byte": "55", "comment": ""},
        {"name": "start_1_time", "byte": "56:57", "comment": ""},
        {"name": "stop_1_time", "byte": "58:59", "comment": ""},
        {"name": "start_2_time", "byte": "60:61", "comment": ""},
        {"name": "stop_2_time", "byte": "62:63", "comment": ""},
        {"name": "backwash_every_n_days", "byte": "68", "comment": ""},
        {"name": "backwash_time", "byte": "69:70", "comment": ""},
        {"name": "backwash_duration", "byte": "71", "comment": ""},
        {"name": "delay_after_startup", "byte": "74:75", "comment": ""},
        {"name": "pool_volume", "byte": "92:93", "comment": ""},
        {"name": "max_filling_time", "byte": "94:95", "comment": "! Duplicate Byte 95"},
        {"name": "flowrate_chlor", "byte": "95", "comment": ""},
        {"name": "flowrate_ph_plus", "byte": "97", "comment": ""},
        {"name": "flowrate_ph_minus", "byte": "99", "comment": ""},
        {"name": "flowrate_floc", "byte": "101", "comment": "Agicide flowrate missing"},
        {"name": "delay_after_dose", "byte": "106:107", "comment": ""},
    ]

    print("def _make_from_hex_dump() -> bytearray:")
    print('    """Create a base bytearray from hex dump."""')
    print("    data = bytearray([0xFF] * 120)")
    for entry in byte_map:
        name = entry["name"]

        if ":" not in entry["byte"]:
            start = int(entry["byte"])
            end = start
            typ = "byte"
        else:
            start, end = map(int, entry["byte"].split(":"))
            end += 1
            typ = "word"

        if typ == "byte":
            value = data[start]
            print(f"    data[{start}] = {value}  # {name} / HEX: 0x{value:02x}")
        elif typ == "word":
            value = int.from_bytes(data[start:end], "big")
            hex_str = data[start:end].hex()
            print(
                f"    data[{start}:{end}] = ({value}).to_bytes({end - start}, 'big')  # {name} / HEX: 0x{hex_str}"
            )
    print("    return data")


# Beispiel-Mapping für die wichtigsten Felder


if __name__ == "__main__":
    import sys
    import os

    # Example usage:
    # python3 hex_dump.py <function> <hexstring> [byte_index]
    # functions: --table, --tablewrite, --byteinfo
    # Example: python3 hex_dump.py 06918724ff... 10

    if len(sys.argv) < 2:
        print("Usage: python3 hex_dump.py <function> <hexstring> [byte_index]")
        print("Functions: --table, --tablewrite, --byteinfo, --generateTest")
        sys.exit(1)

    # find option position in parameters
    if "--" in sys.argv[1]:
        option_pos = 1
    elif "--" in sys.argv[2]:
        option_pos = 2
    elif len(sys.argv) > 3 and "--" in sys.argv[3]:
        option_pos = 3
    else:
        print("Usage: python3 hex_dump.py <function> <hexstring> [byte_index]")
        print("Functions: --table, --tablewrite, --byteinfo, --generateTest")
        sys.exit(1)

    # find hex dump position in parameters
    if len(sys.argv[1]) / 2 >= 120:
        hex_string = sys.argv[1].replace(" ", "")
        data = bytearray.fromhex(hex_string)
        hex_pos = 1
    elif len(sys.argv[2]) / 2 >= 120:
        hex_string = sys.argv[2].replace(" ", "")
        data = bytearray.fromhex(hex_string)
        hex_pos = 2
    elif len(sys.argv) > 3 and len(sys.argv[3]) / 2 >= 120:
        hex_string = sys.argv[3].replace(" ", "")
        data = bytearray.fromhex(hex_string)
        hex_pos = 3
    else:
        print(f"Invalid HEX dump. More or less 120 Bytes. ({len(hex_dump) / 2} bytes)")
        print("Usage: python3 hex_tools.py <function> <hexstring> [byte_index]")
        print("Functions: --table, --tablewrite, --byteinfo, --generateTest")
        sys.exit(1)

    # find byte index position in parameters
    if len(sys.argv) > 3:
        if (option_pos == 1 and hex_pos == 2) or (option_pos == 2 and hex_pos == 1):
            index_pos = 3
            byte_index = int(sys.argv[3])
        elif (option_pos == 1 and hex_pos == 3) or (option_pos == 3 and hex_pos == 1):
            index_pos = 2
            byte_index = int(sys.argv[2])

        elif (option_pos == 2 and hex_pos == 3) or (option_pos == 3 and hex_pos == 2):
            index_pos = 1
            byte_index = int(sys.argv[1])
        else:
            index_pos = None

    # Write hex table to hex_table.md in the same directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    md_path = os.path.join(script_dir, "hex_table.md")

    funct = sys.argv[option_pos]
    if funct.startswith("--"):
        print(funct)
        if funct == "--table":
            print_hex_table_full(data)
        elif funct == "--tablewrite":
            write_hex_table_md(data, md_path)
            print(f"\nHex table written to {md_path}")
        elif funct == "--byteinfo":
            if len(sys.argv) != 3 and index_pos is None:
                print("Usage: python3 hex_tools.py --byteinfo <hexstring> <byte_index>")
                sys.exit(1)
            print_byte_info(data, byte_index)
        elif funct == "--generateTest":
            generate_bytearray(data)
        elif funct == "--hex":
            print(len(hex_string) / 2)
            print(hex_string)
        elif funct == "--help":
            print("Available functions: --table, --tablewrite, --byteinfo")
            print("Functions: --table, --tablewrite, --byteinfo, --generateTest")
        else:
            print("Usage: python3 hex_tools.py <function> <hexstring> [byte_index]")
            print("Functions: --table, --tablewrite, --byteinfo, --generateTest")
            sys.exit(1)
