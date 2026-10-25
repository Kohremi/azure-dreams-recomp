// Create a function at every pointer of a jump table (e.g. a bytecode opcode table) and name
// them <prefix>_<index in hex>.
// Args: <hex table addr> <count> <prefix>
//@category Azure
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class FunctionsFromTable extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Address table = toAddr(Long.parseLong(a[0].replace("0x", ""), 16));
        int count = Integer.parseInt(a[1]);
        String prefix = a[2];
        int made = 0;
        for (int i = 0; i < count; i++) {
            Address target = toAddr(getInt(table.add(i * 4L)) & 0xFFFFFFFFL);
            Function f = getFunctionAt(target);
            if (f == null) {
                Function containing = getFunctionContaining(target);
                if (containing != null && !containing.getEntryPoint().equals(target))
                    removeFunction(containing);   // a handler swallowed into a neighbour
                disassemble(target);
                f = createFunction(target, null);
                if (f != null) made++;
            }
            if (f != null && f.getName().startsWith("FUN_") || f != null && f.getName().startsWith("LAB_"))
                f.setName(String.format("%s_%02x", prefix, i), SourceType.USER_DEFINED);
        }
        println("table " + table + ": created " + made + " functions");
    }
}
