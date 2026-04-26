<script lang="ts">
  import type { Theme } from "../api";
  import { themeToCssVars } from "../theme";

  export let theme: Theme;

  $: vars = themeToCssVars(theme);
</script>

<div class="themed-wrap" style={vars}>
  <slot />
</div>

<style>
  .themed-wrap {
    background: var(--wb-bg, #fff);
    color: var(--wb-ink, #111);
    font-family: var(--wb-font-body, ui-sans-serif, system-ui, sans-serif);
    min-height: calc(100vh - 49px);
  }
</style>
