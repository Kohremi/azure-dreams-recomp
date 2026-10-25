// Decompile other species' code chunks in a program that already has the EXE + dungeon module and
// a chunk block at 0x80170800 (SLUS_barong.exe): for each <chunk.bin> <out.c> pair, clear the
// block's functions and listing, write the chunk, create functions at every prologue and at every
// code pointer in its first 0x200 bytes (the handler tables), and decompile the block.
// Args: <chunk.bin> <out.c> [<chunk.bin> <out.c> ...]
//@category Azure
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import java.io.*;
import java.nio.file.*;

public class SwapChunk extends GhidraScript {
    static final long LO = 0x80170800L, HI = 0x80176800L;

    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        for (int i = 0; i + 1 < a.length; i += 2) {
            swap(a[i], a[i + 1]);
        }
    }

    void swap(String bin, String out) throws Exception {
        Address lo = toAddr(LO), hi = toAddr(HI - 1);
        AddressSet range = new AddressSet(lo, hi);
        FunctionManager fm = currentProgram.getFunctionManager();
        for (Function f : fm.getFunctions(range, true)) {
            fm.removeFunction(f.getEntryPoint());
        }
        clearListing(range);
        byte[] data = Files.readAllBytes(Paths.get(bin));
        currentProgram.getMemory().setBytes(lo, data);
        int n = 0;
        // Code pointers in the header / handler tables.
        for (long p = LO; p < LO + 0x200; p += 4) {
            long v = getInt(toAddr(p)) & 0xFFFFFFFFL;
            if (v >= LO && v < HI && (v & 3) == 0 && getFunctionAt(toAddr(v)) == null) {
                disassemble(toAddr(v));
                if (createFunction(toAddr(v), null) != null) n++;
            }
        }
        for (long p = LO; p < HI; p += 4) {
            Address ad = toAddr(p);
            int w = getInt(ad);
            if ((w & 0xFFFF8000) == 0x27BD8000 && getFunctionContaining(ad) == null) {
                disassemble(ad);
                if (createFunction(ad, null) != null) n++;
            }
        }
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        int ok = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(out))) {
            for (Function f : fm.getFunctions(range, true)) {
                DecompileResults r = d.decompileFunction(f, 60, monitor);
                w.println("// ==== " + f.getEntryPoint() + " " + f.getName());
                if (r != null && r.decompileCompleted()) {
                    w.println(r.getDecompiledFunction().getC());
                    ok++;
                } else {
                    w.println("// decompile failed");
                }
            }
        }
        d.dispose();
        println(bin + ": " + n + " functions created, " + ok + " decompiled -> " + out);
    }
}
