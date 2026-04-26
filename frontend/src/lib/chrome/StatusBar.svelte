<script lang="ts">
  import type { Theme, WorkbenchMeta } from "../api";
  import { themeToCssVars } from "../theme";

  export let theme: Theme | null = null;
  export let workbench: WorkbenchMeta | null = null;

  $: vars = theme ? themeToCssVars(theme) : "";

  // A pseudo-frequency derived from the active workbench slug.
  $: freq = workbench
    ? `FREQ_${(workbench.slug
        .split("")
        .reduce((a, c) => (a + c.charCodeAt(0)) % 9999, 0)
        .toString()
        .padStart(4, "0"))}`
    : "FREQ_2929";
  $: sector = workbench ? `SECTOR_${workbench.slug.toUpperCase()}` : "SECTOR_GLOBAL";
</script>

<footer class:themed={!!theme} style={vars}>
  <div class="pip ok">
    <span class="dot"></span>
    <span class="label-maker">SCAN_PROBE</span>
  </div>
  <div class="pip ok">
    <span class="dot"></span>
    <span class="label-maker">COMMS_LINK</span>
  </div>
  <div class="pip warn">
    <span class="dot"></span>
    <span class="label-maker">VAULT_PROTOCOL_ALERT</span>
  </div>
  <span class="spacer"></span>
  <div class="freq">
    <span class="label-maker">{sector}</span>
    <span class="sep">//</span>
    <span class="crt">{freq}</span>
  </div>
</footer>

<style>
  footer {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 8px 18px;
    background: var(--ab-surface);
    border-top: 2px solid #000;
    color: var(--ab-muted);
    font-size: 11px;
    flex-wrap: wrap;
    background-image: linear-gradient(180deg, rgba(255, 244, 214, 0.04), transparent 60%);
  }
  footer.themed {
    background: var(--wb-surface, var(--ab-surface));
    color: var(--wb-muted, var(--ab-muted));
  }
  .pip { display: inline-flex; align-items: center; gap: 6px; }
  .pip .dot { width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 0 2px #000; }
  .pip.ok { color: var(--ab-green); }
  .pip.ok .dot { background: var(--ab-green); box-shadow: 0 0 6px var(--ab-green), 0 0 0 2px #000; }
  .pip.warn { color: var(--ab-yellow); }
  .pip.warn .dot { background: var(--ab-yellow); box-shadow: 0 0 6px var(--ab-yellow), 0 0 0 2px #000; }
  .spacer { flex: 1; }
  .freq { display: inline-flex; align-items: center; gap: 8px; color: var(--ab-cyan); }
  .freq .sep { opacity: 0.5; font-family: var(--ab-font-mono); }
  .freq .crt { font-family: var(--ab-font-crt); font-size: 14px; letter-spacing: 0.04em; color: var(--ab-cyan); }

  @media (max-width: 540px) {
    footer { gap: 10px; padding: 6px 10px; }
  }
</style>
