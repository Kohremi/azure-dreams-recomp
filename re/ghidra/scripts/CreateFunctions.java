// Disassemble and create functions at every "addiu sp,sp,-N" prologue in a range
// (overlay code that auto-analysis never reaches because nothing calls into it yet).
// Args: <hex lo> <hex hi>
//@category Azure
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class CreateFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        long lo = Long.parseLong(a[0].replace("0x", ""), 16), hi = Long.parseLong(a[1].replace("0x", ""), 16);
        int n = 0;
        for (long p = lo; p < hi; p += 4) {
            Address ad = toAddr(p);
            int w;
            try {
                w = getInt(ad);
            } catch (Exception e) {
                continue;   // outside the loaded blocks
            }
            if ((w & 0xFFFF8000) == 0x27BD8000 && getFunctionContaining(ad) == null) {
                disassemble(ad);
                if (createFunction(ad, null) != null) n++;
            }
        }
        println("created " + n + " functions in range");
    }
}
