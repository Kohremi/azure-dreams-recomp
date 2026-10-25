// Apply splat-style symbol files: "name = 0x80012345; // type:func"
// Args: <symbol file> [more files...]
//@category Azure
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.*;
import java.util.regex.*;

public class ApplySymbols extends GhidraScript {
    @Override
    public void run() throws Exception {
        Pattern p = Pattern.compile("^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*0x([0-9A-Fa-f]+)\s*;(.*)$");
        int n = 0;
        for (String f : getScriptArgs()) {
            for (String line : Files.readAllLines(Paths.get(f))) {
                Matcher m = p.matcher(line);
                if (!m.matches()) continue;
                Address addr = toAddr(Long.parseLong(m.group(2), 16));
                if (currentProgram.getMemory().getBlock(addr) == null) continue;
                boolean func = m.group(3).contains("type:func");
                if (func) {
                    disassemble(addr);
                    if (getFunctionAt(addr) == null) createFunction(addr, m.group(1));
                    var fn = getFunctionAt(addr);
                    if (fn != null) fn.setName(m.group(1), SourceType.USER_DEFINED);
                } else {
                    createLabel(addr, m.group(1), true, SourceType.USER_DEFINED);
                }
                n++;
            }
        }
        println("applied " + n + " symbols");
    }
}
