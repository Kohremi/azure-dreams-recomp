// Overlay a raw module file onto the program's RAM at a fixed address before analysis.
// Args: <module.bin> <hex load address>
//@category Azure
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.*;
import java.nio.file.*;

public class LoadModule extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        byte[] data = Files.readAllBytes(Paths.get(a[0]));
        Address start = toAddr(Long.parseLong(a[1].replace("0x", ""), 16));
        Address end = start.add(data.length - 1);
        Memory mem = currentProgram.getMemory();
        MemoryBlock b = mem.getBlock(start);
        if (b == null) {
            MemoryBlock nb = mem.createInitializedBlock("module", start, data.length, (byte) 0, monitor, false);
            nb.setRead(true); nb.setWrite(true); nb.setExecute(true);
        } else if (!b.isInitialized()) {
            if (!b.getStart().equals(start)) { mem.split(b, start); b = mem.getBlock(start); }
            if (b.getEnd().compareTo(end) > 0) mem.split(b, end.add(1));
            b = mem.getBlock(start);
            b = mem.convertToInitialized(b, (byte) 0);
            b.setName("module");
            b.setExecute(true);
        }
        mem.setBytes(start, data);
        println("module " + a[0] + " loaded at " + start + " (" + data.length + " bytes)");
    }
}
