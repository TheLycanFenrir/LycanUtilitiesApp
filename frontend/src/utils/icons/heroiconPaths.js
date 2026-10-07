import sun from "../../../public/assets/heroicons/optimized/24/outline/sun.svg?raw";
import moon from "../../../public/assets/heroicons/optimized/24/outline/moon.svg?raw";
import magnifyingGlass from "../../../public/assets/heroicons/optimized/24/outline/magnifying-glass.svg?raw";
import squares2x2 from "../../../public/assets/heroicons/optimized/24/outline/squares-2x2.svg?raw";
import bars3 from "../../../public/assets/heroicons/optimized/24/outline/bars-3.svg?raw";
import star from "../../../public/assets/heroicons/optimized/24/outline/star.svg?raw";
import clock from "../../../public/assets/heroicons/optimized/24/outline/clock.svg?raw";
import xMark from "../../../public/assets/heroicons/optimized/24/outline/x-mark.svg?raw";
import arrowLeft from "../../../public/assets/heroicons/optimized/24/outline/arrow-left.svg?raw";
import check from "../../../public/assets/heroicons/optimized/24/outline/check.svg?raw";
import cpuChip from "../../../public/assets/heroicons/optimized/24/outline/cpu-chip.svg?raw";
import eyeDropper from "../../../public/assets/heroicons/optimized/24/outline/eye-dropper.svg?raw";
import serverStack from "../../../public/assets/heroicons/optimized/24/outline/server-stack.svg?raw";
import queueList from "../../../public/assets/heroicons/optimized/24/outline/queue-list.svg?raw";
import play from "../../../public/assets/heroicons/optimized/24/outline/play.svg?raw";
import pause from "../../../public/assets/heroicons/optimized/24/outline/pause.svg?raw";
import stop from "../../../public/assets/heroicons/optimized/24/outline/stop.svg?raw";
import bolt from "../../../public/assets/heroicons/optimized/24/outline/bolt.svg?raw";
import chevronUp from "../../../public/assets/heroicons/optimized/24/outline/chevron-up.svg?raw";
import chevronDown from "../../../public/assets/heroicons/optimized/24/outline/chevron-down.svg?raw";
import pencil from "../../../public/assets/heroicons/optimized/24/outline/pencil.svg?raw";
import ellipsisHorizontal from "../../../public/assets/heroicons/optimized/24/outline/ellipsis-horizontal.svg?raw";
import exclamationTriangle from "../../../public/assets/heroicons/optimized/24/outline/exclamation-triangle.svg?raw";
import videoCamera from "../../../public/assets/heroicons/optimized/24/outline/video-camera.svg?raw";
import photo from "../../../public/assets/heroicons/optimized/24/outline/photo.svg?raw";
import documentText from "../../../public/assets/heroicons/optimized/24/outline/document-text.svg?raw";
import cube from "../../../public/assets/heroicons/optimized/24/outline/cube.svg?raw";
import sparkles from "../../../public/assets/heroicons/optimized/24/outline/sparkles.svg?raw";
import archiveBox from "../../../public/assets/heroicons/optimized/24/outline/archive-box.svg?raw";
import wrenchScrewdriver from "../../../public/assets/heroicons/optimized/24/outline/wrench-screwdriver.svg?raw";
import arrowDownTray from "../../../public/assets/heroicons/optimized/24/outline/arrow-down-tray.svg?raw";
import arrowPath from "../../../public/assets/heroicons/optimized/24/outline/arrow-path.svg?raw";
import bookOpen from "../../../public/assets/heroicons/optimized/24/outline/book-open.svg?raw";
import shoppingBag from "../../../public/assets/heroicons/optimized/24/outline/shopping-bag.svg?raw";
import codeBracket from "../../../public/assets/heroicons/optimized/24/outline/code-bracket.svg?raw";

// App icon name -> heroicons file under public/assets/heroicons.
export const HEROICON_SRCS = {
  sun: sun,
  moon: moon,
  search: magnifyingGlass,
  grid: squares2x2,
  list: bars3,
  star: star,
  clock: clock,
  x: xMark,
  "arrow-left": arrowLeft,
  check: check,
  cpu: cpuChip,
  eyedropper: eyeDropper,
  "server-stack": serverStack,
  "queue-list": queueList,
  play: play,
  pause: pause,
  stop: stop,
  bolt: bolt,
  "chevron-up": chevronUp,
  "chevron-down": chevronDown,
  pencil: pencil,
  ellipsis: ellipsisHorizontal,
  "exclamation-triangle": exclamationTriangle,
  "video-camera": videoCamera,
  photo: photo,
  "document-text": documentText,
  cube: cube,
  sparkles: sparkles,
  "archive-box": archiveBox,
  "wrench-screwdriver": wrenchScrewdriver,
  download: arrowDownTray,
  "arrow-path": arrowPath,
  "book-open": bookOpen,
  "shopping-bag": shoppingBag,
  "code-bracket": codeBracket,
};

// Icons that do not exist in the heroicons set are defined locally.
export const CUSTOM_PATHS = {
  folder: "M2.25 7.5a2.25 2.25 0 0 1 2.25-2.25h4.5a2.25 2.25 0 0 1 1.83.914l1.016 1.355a.75.75 0 0 0 .61.305h6.297A2.25 2.25 0 0 1 21 10.07V16.5a2.25 2.25 0 0 1-2.25 2.25H4.5A2.25 2.25 0 0 1 2.25 16.5v-9Z",
  github: "M12 .5A11.5 11.5 0 0 0 .5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56 0-.27-.01-1.15-.02-2.08-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.7 1.25 3.36.96.1-.75.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.97 10.97 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.76.11 3.05.73.81 1.18 1.84 1.18 3.1 0 4.43-2.69 5.41-5.25 5.69.41.35.77 1.05.77 2.12 0 1.53-.01 2.76-.01 3.14 0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12 11.5 11.5 0 0 0 12 .5Z",
  ram: "M4 5.5h16A1.5 1.5 0 0 1 21.5 7v10a1.5 1.5 0 0 1-1.5 1.5H4A1.5 1.5 0 0 1 2.5 17V7A1.5 1.5 0 0 1 4 5.5ZM2.5 12h19M7 5.5v-2M11 5.5v-2M15 5.5v-2M19 5.5v-2",
};

export function svgBody(src) {
  const m = src.match(/<svg[^>]*>([\s\S]*)<\/svg>/);
  return m ? m[1].trim() : "";
}