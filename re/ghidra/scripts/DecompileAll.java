// Decompile every function into one C file for grep-driven reverse engineering.
// Args: <output .c path> [hex lo] [hex hi]  (optional entry-point range filter)
//@category Azure
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import java.io.*;

public class DecompileAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String out = args[0];
        long lo = args.length > 2 ? Long.parseLong(args[1].replace("0x", ""), 16) : 0;
        long hi = args.length > 2 ? Long.parseLong(args[2].replace("0x", ""), 16) : Long.MAX_VALUE;
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        int n = 0, fail = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(out))) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                if (monitor.isCancelled()) break;
                long ep = f.getEntryPoint().getOffset();
                if (ep < lo || ep >= hi) continue;
                DecompileResults r = d.decompileFunction(f, 60, monitor);
                w.println("// ==== " + f.getEntryPoint() + " " + f.getName() + " (block "
                        + currentProgram.getMemory().getBlock(f.getEntryPoint()).getName() + ")");
                if (r != null && r.decompileCompleted()) {
                    w.println(r.getDecompiledFunction().getC());
                    n++;
                } else {
                    w.println("// decompile failed: " + (r == null ? "null" : r.getErrorMessage()));
                    fail++;
                }
            }
        }
        println("decompiled " + n + " functions, " + fail + " failed -> " + out);
    }
}
