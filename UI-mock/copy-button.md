You are given a task to integrate an existing React component in the codebase

The codebase should support:
- shadcn project structure  
- Tailwind CSS
- Typescript

If it doesn't, provide instructions on how to setup project via shadcn CLI, install Tailwind or Typescript.

Determine the default path for components and styles. 
If default path for components is not /components/ui, provide instructions on why it's important to create this folder
Copy-paste this component to /components/ui folder:
```tsx
dot-border-button.tsx
import { useMemo, type CSSProperties } from "react";

type FocusRole = "background" | "button" | "visual";
type EffectMode = "light" | "dark";

type FocusTarget = {
  selector: string;
  role: FocusRole;
  preserveTransform?: boolean;
};

type EffectDefinition = {
  title: string;
  source: string;
  background: string;
  targets: readonly FocusTarget[];
  theme?: {
    lightBackground: string;
    darkBackground: string;
  };
};

export type DotBorderButtonProps = {
  mode?: EffectMode;
  hue?: number;
  saturation?: number;
  brightness?: number;
  className?: string;
  style?: CSSProperties;
};

const DOT_BORDER_BUTTON_DEFAULTS = {
  mode: "dark",
  hue: 0,
  saturation: 1,
  brightness: 1,
} as const;

// Verbatim from MengTo/threeui:
// src/shaders/neuform-isolated/sources/dot-border-button.html
const DOT_BORDER_BUTTON_SOURCE = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Component Preview</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    html, body {
      height: 100%;
      margin: 0;
      padding: 0;
    }
    body {
      height: 100%;
      overflow: auto;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #000000;
      color: #ffffff;
    }
    .component-wrapper {
      width: 100%;
      height: 100%;
      padding: 0;
      box-sizing: border-box;
      overflow: auto;
    }
  </style>
</head>
<body>
  <div class="component-wrapper">
    <html><head></head><body><div style="
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background-color: #000; /* optional, just for visibility */
"><a href="#" class="btn-wrapper" style="--dot-size: 8px; --line-weight: 1px; --line-distance: 0.8rem 1rem; --animation-speed: 0.35s; --dot-color: #fffa; --line-color: #fffa; --grid-color: #fff3; position: relative; display: inline-flex; justify-content: center; align-items: center; width: auto; height: auto; padding: var(--line-distance); background-color: rgba(0, 0, 0, 0); user-select: none">
  <style>
    .btn-wrapper::after {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      border-radius: inherit;
      pointer-events: none;
      background-color: #0000;
      background-image: repeating-linear-gradient(45deg, var(--grid-color) 0 1px, transparent 2px 5px);
      opacity: 0;
      z-index: -1;
    }

    .btn-wrapper:has(.btn:hover)::after {
      animation: opacity-anim calc(var(--animation-speed) * 4) ease-in-out forwards;
    }

    @keyframes opacity-anim {
      80% {
        opacity: 0;
      }

      100% {
        opacity: 1;
      }
    }

    .btn-wrapper .btn {
      position: relative;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 0.8rem 1.25rem;
      background-color: #fff0;
      border: 1px solid var(--grid-color);
      color: #fffd;
      font-family: "Inter", sans-serif;
      letter-spacing: -0.01em;
      font-size: 1rem;
      font-weight: 600;
      text-transform: capitalize;
      border-radius: 6px;
      cursor: pointer;
      transition: transform .2s ease-in-out, letter-spacing .2s ease-in-out;
    }

    .btn-wrapper .btn:hover {
      background-color: #25358b;
      color: #fff;
      transform: scale(1.05);
      letter-spacing: .06em;
    }

    .btn-wrapper .btn:active {
      background-color: #25358b;
      transform: scale(.98);
      letter-spacing: .02em;
    }

    .btn-wrapper .btn-svg {
      margin-left: .5rem;
      height: 24px;
      stroke-width: 1;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke: #fff4;
      fill: #fff2;
      transition: all .2s ease-in-out;
    }

    .btn-wrapper .btn:hover .btn-svg {
      stroke: #fffa;
      fill: #fff3;
    }

    .btn-wrapper .dot {
      position: absolute;
      width: var(--dot-size);
      aspect-ratio: 1;
      border-radius: 2px;
      background-color: var(--dot-color);
      transition: all .3s ease-in-out;
      opacity: 0;
    }

    .btn-wrapper:has(.btn:hover) .dot.top.left {
      top: 50%;
      left: 20%;
      animation: move-top-left var(--animation-speed) ease-in-out forwards;
    }

    @keyframes move-top-left {
      90% {
        opacity: .6;
      }

      100% {
        top: calc(var(--dot-size) * -0.5);
        left: calc(var(--dot-size) * -0.5);
        opacity: 1;
      }
    }

    .btn-wrapper:has(.btn:hover) .dot.top.right {
      top: 50%;
      right: 20%;
      animation: move-top-right var(--animation-speed) ease-in-out forwards;
      animation-delay: calc(var(--animation-speed)*.6);
    }

    @keyframes move-top-right {
      80% {
        opacity: .6;
      }

      100% {
        top: calc(var(--dot-size) * -0.5);
        right: calc(var(--dot-size) * -0.5);
        opacity: 1;
      }
    }

    .btn-wrapper:has(.btn:hover) .dot.bottom.right {
      bottom: 50%;
      right: 20%;
      animation: move-bottom-right var(--animation-speed) ease-in-out forwards;
      animation-delay: calc(var(--animation-speed)*1.2);
    }

    @keyframes move-bottom-right {
      80% {
        opacity: .6;
      }

      100% {
        bottom: calc(var(--dot-size) * -0.5);
        right: calc(var(--dot-size) * -0.5);
        opacity: 1;
      }
    }

    .btn-wrapper:has(.btn:hover) .dot.bottom.left {
      bottom: 50%;
      left: 20%;
      animation: move-bottom-left var(--animation-speed) ease-in-out forwards;
      animation-delay: calc(var(--animation-speed)*1.8);
    }

    @keyframes move-bottom-left {
      80% {
        opacity: .6;
      }

      100% {
        bottom: calc(var(--dot-size) * -0.5);
        left: calc(var(--dot-size) * -0.5);
        opacity: 1;
      }
    }

    .btn-wrapper .line {
      position: absolute;
      transition: all .3s ease-in-out;
    }

    .btn-wrapper .line.horizontal {
      height: var(--line-weight);
      width: 100%;
      background-image: repeating-linear-gradient(90deg, #0000 0 calc(var(--line-weight)*2), var(--line-color) calc(var(--line-weight)*2) calc(var(--line-weight)*4));
    }

    .btn-wrapper .line.top {
      top: calc(var(--line-weight)*-0.5);
      transform-origin: top left;
      transform: rotate(5deg) scaleX(0);
    }

    .btn-wrapper:has(.btn:hover) .line.top {
      animation: draw-top var(--animation-speed) ease-in-out forwards;
      animation-delay: calc(var(--animation-speed)*.8);
    }

    @keyframes draw-top {
      100% {
        transform: rotate(0deg) scaleX(1);
      }
    }

    .btn-wrapper .line.bottom {
      bottom: calc(var(--line-weight)*-0.5);
      transform-origin: bottom right;
      transform: rotate(5deg) scaleX(0);
    }

    .btn-wrapper:has(.btn:hover) .line.bottom {
      animation: draw-bottom var(--animation-speed) ease-in-out forwards;
      animation-delay: calc(var(--animation-speed)*2);
    }

    @keyframes draw-bottom {
      100% {
        transform: rotate(0deg) scaleX(1);
      }
    }

    .btn-wrapper .line.vertical {
      width: var(--line-weight);
      height: 100%;
      background-image: repeating-linear-gradient(0deg, #0000 0 calc(var(--line-weight)*2), var(--line-color) calc(var(--line-weight)*2) calc(var(--line-weight)*4));
    }

    .btn-wrapper .line.left {
      left: calc(var(--line-weight)*-0.5);
      transform-origin: bottom left;
      transform: rotate(0deg) scaleY(0);
    }

    .btn-wrapper:has(.btn:hover) .line.left {
      animation: draw-left var(--animation-speed) ease-in-out forwards;
      animation-delay: calc(var(--animation-speed)*2.4);
    }

    @keyframes draw-left {
      100% {
        transform: rotate(0deg) scaleY(1);
      }
    }

    .btn-wrapper .line.right {
      right: calc(var(--line-weight)*-0.5);
      transform-origin: top right;
      transform: rotate(5deg) scaleY(0);
    }

    .btn-wrapper:has(.btn:hover) .line.right {
      animation: draw-right var(--animation-speed) ease-in-out forwards;
      animation-delay: calc(var(--animation-speed)*1.4);
    }

    @keyframes draw-right {
      100% {
        transform: rotate(0deg) scaleY(1);
      }
    }
  </style>

  <div class="line horizontal top"></div>
  <div class="line vertical right"></div>
  <div class="line horizontal bottom"></div>
  <div class="line vertical left"></div>

  <div class="dot top left"></div>
  <div class="dot top right"></div>
  <div class="dot bottom right"></div>
  <div class="dot bottom left"></div>

  <button class="btn bg-[#ffffff]">
            <span class="btn-text">Start Creating</span>
            <svg class="btn-svg" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M17.6744 11.4075L15.7691 17.1233C15.7072 17.309 15.5586 17.4529 15.3709 17.5087L3.69348 20.9803C3.22819 21.1186 2.79978 20.676 2.95328 20.2155L6.74467 8.84131C6.79981 8.67588 6.92419 8.54263 7.08543 8.47624L12.472 6.25822C12.696 6.166 12.9535 6.21749 13.1248 6.38876L17.5294 10.7935C17.6901 10.9542 17.7463 11.1919 17.6744 11.4075Z" class=""></path>
              <path d="M3.2959 20.6016L9.65986 14.2376" class=""></path>
              <path d="M17.7917 11.0557L20.6202 8.22724C21.4012 7.44619 21.4012 6.17986 20.6202 5.39881L18.4989 3.27749C17.7178 2.49645 16.4515 2.49645 15.6704 3.27749L12.842 6.10592" class=""></path>
              <path d="M11.7814 12.1163C11.1956 11.5305 10.2458 11.5305 9.66004 12.1163C9.07426 12.7021 9.07426 13.6519 9.66004 14.2376C10.2458 14.8234 11.1956 14.8234 11.7814 14.2376C12.3671 13.6519 12.3671 12.7021 11.7814 12.1163Z" class=""></path>
            </svg>
          </button>
</a></div></body></html>
  </div>
</body>
</html>
`;

const DOT_BORDER_BUTTON_DEFINITION: EffectDefinition = {
  title: "Dot Border button",
  source: DOT_BORDER_BUTTON_SOURCE,
  background: "#111318",
  theme: { lightBackground: "#f4f7fb", darkBackground: "#111318" },
  targets: [
    {
      selector: ".component-wrapper .btn-wrapper",
      role: "button",
      preserveTransform: true,
    },
  ],
};

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function effectBackground(definition: EffectDefinition, mode: EffectMode) {
  return definition.theme?.[`${mode}Background`] ?? definition.background;
}

function buildFocusedDocument(definition: EffectDefinition, mode: EffectMode) {
  const background = effectBackground(definition, mode);
  const targetJson = JSON.stringify(definition.targets).replace(
    /</g,
    "\\u003c",
  );
  const modeJson = JSON.stringify(mode);
  const focusStyle = `<style data-threeui-focus>
html, body { width: 100% !important; height: 100% !important; min-height: 0 !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; background: ${background} !important; color-scheme: ${mode} !important; }
body { position: relative !important; display: flex !important; align-items: center !important; justify-content: center !important; }
body > * { visibility: hidden !important; }
body[data-threeui-ready] > [data-threeui-role] { visibility: visible !important; }
[data-threeui-residual] { display: none !important; }
[data-threeui-role="button"] { position: relative !important; z-index: 2 !important; opacity: 1 !important; flex: none !important; }
[data-threeui-role="button"]:not([data-threeui-preserve-transform]) { transform: none !important; }
</style>`;
  const focusScript = `<script data-threeui-focus>
(function () {
  document.documentElement.dataset.sfMode = ${modeJson};
  var isolated = false;
  function isolate() {
    if (isolated) return;
    var specs = ${targetJson};
    var roots = [];
    specs.forEach(function (spec) {
      var element = document.querySelector(spec.selector);
      if (!element) return;
      element.setAttribute('data-threeui-role', spec.role);
      if (spec.preserveTransform) element.setAttribute('data-threeui-preserve-transform', '');
      if (!roots.some(function (root) { return root.contains(element); })) roots.push(element);
    });
    if (!roots.length) return;
    isolated = true;
    roots.forEach(function (root) {
      var placeholderLink = root.matches('a[href="#"]') ? root : root.querySelector('a[href="#"]');
      if (placeholderLink) placeholderLink.addEventListener('click', function (event) { event.preventDefault(); });
      document.body.appendChild(root);
    });
    Array.from(document.body.children).forEach(function (element) {
      if (roots.indexOf(element) !== -1) return;
      element.setAttribute('data-threeui-residual', '');
      element.setAttribute('aria-hidden', 'true');
      if ('inert' in element) element.inert = true;
    });
    document.body.setAttribute('data-threeui-ready', '');
    requestAnimationFrame(function () { window.dispatchEvent(new Event('resize')); });
  }
  function scheduleIsolation() { setTimeout(isolate, 100); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scheduleIsolation, { once: true });
  else scheduleIsolation();
  window.addEventListener('load', isolate, { once: true });
})();
</script>`;
  return definition.source
    .replace(/<\/head>/i, `${focusStyle}</head>`)
    .replace(/<\/body>/i, `${focusScript}</body>`);
}

function NeuformIsolatedEffect({
  definition,
  mode = DOT_BORDER_BUTTON_DEFAULTS.mode,
  hue = DOT_BORDER_BUTTON_DEFAULTS.hue,
  saturation = DOT_BORDER_BUTTON_DEFAULTS.saturation,
  brightness = DOT_BORDER_BUTTON_DEFAULTS.brightness,
  className,
  style,
}: DotBorderButtonProps & { definition: EffectDefinition }) {
  const safeMode: EffectMode = mode === "light" ? "light" : "dark";
  const background = effectBackground(definition, safeMode);
  const source = useMemo(
    () => buildFocusedDocument(definition, safeMode),
    [definition, safeMode],
  );
  const safeHue = clamp(hue, -180, 180);
  const safeSaturation = clamp(saturation, 0, 2);
  const safeBrightness = clamp(brightness, 0.35, 1.65);
  const filter =
    safeHue === 0 && safeSaturation === 1 && safeBrightness === 1
      ? undefined
      : `hue-rotate(${safeHue}deg) saturate(${safeSaturation}) brightness(${safeBrightness})`;

  return (
    <iframe
      className={className}
      data-mode={safeMode}
      title={definition.title}
      srcDoc={source}
      sandbox="allow-scripts"
      loading="eager"
      style={{
        display: "block",
        width: "100%",
        height: "100%",
        border: 0,
        background,
        filter,
        ...style,
      }}
    />
  );
}

function DotBorderButton(props: DotBorderButtonProps) {
  return (
    <NeuformIsolatedEffect
      {...props}
      definition={DOT_BORDER_BUTTON_DEFINITION}
    />
  );
}

export default DotBorderButton;


demo.tsx
import DotBorderButton from "@/components/ui/dot-border-button";

export default function DotBorderButtonDemo() {
  return (
    <div className="flex h-[420px] w-full items-center justify-center overflow-hidden rounded-xl border border-border bg-[#111318]">
      <DotBorderButton mode="dark" className="h-full w-full" />
    </div>
  );
}

```

Implementation Guidelines
 1. Analyze the component structure and identify all required dependencies
 2. Review the component's argumens and state
 3. Identify any required context providers or hooks and install them
 4. Questions to Ask
 - What data/props will be passed to this component?
 - Are there any specific state management requirements?
 - Are there any required assets (images, icons, etc.)?
 - What is the expected responsive behavior?
 - What is the best place to use this component in the app?

Steps to integrate
 0. Copy paste all the code above in the correct directories
 1. Install external dependencies
 2. Fill image assets with Unsplash stock images you know exist
 3. Use lucide-react icons for svgs or logos if component requires them
