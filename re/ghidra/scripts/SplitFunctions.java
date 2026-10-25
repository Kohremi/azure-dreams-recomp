// Split functions that auto-analysis ran together: wherever an "addiu sp,sp,-N" prologue follows a
// "jr ra" + delay slot but sits inside another function's body, recreate a function there (code
// that is only reached through pointers, e.g. the dungeon's per-unit task functions).
// Args: <hex lo> <hex hi>
//@category Azure
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class SplitFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        long lo = Long.parseLong(a[0].replace("0x", ""), 16), hi = Long.parseLong(a[1].replace("0x", ""), 16);
        int n = 0;
        for (long p = lo + 8; p < hi; p += 4) {
            Address ad = toAddr(p);
            int w, prev2;
            try {
                w = getInt(ad);
                prev2 = getInt(toAddr(p - 8));
            } catch (Exception e) {
                continue;
            }
            if ((w & 0xFFFF8000) != 0x27BD8000 || prev2 != 0x03E00008) {
                continue;
            }
            Function f = getFunctionContaining(ad);
            if (f != null && f.getEntryPoint().equals(ad)) {
                continue;
            }
            Address old = f != null ? f.getEntryPoint() : null;
            if (f != null) {
                removeFunction(f);
            }
            disassemble(ad);
            if (createFunction(ad, null) != null) {
                n++;
            }
            if (old != null && getFunctionAt(old) == null) {
                createFunction(old, null);
            }
        }
        println("split off " + n + " functions in range");
    }
}
