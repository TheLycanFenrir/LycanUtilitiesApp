import { CUSTOM_PATHS, HEROICON_SRCS, svgBody } from "../../utils/icons/heroiconPaths.js";
import wolfHead from "../../assets/icons/wolf-head.svg?raw";
import pythonLogo from "../../assets/icons/python.svg?raw";

export function WolfIcon() {
  return (
    <svg
      viewBox="0 0 512 512"
      className={"svg-icon wolf"}
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: svgBody(wolfHead) }}
    />
  );
}

export function PythonIcon() {
  return (
    <svg
      viewBox="0.21 -0.077 110 110"
      className={"svg-icon python"}
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: svgBody(pythonLogo) }}
    />
  );
}

export function Icon({ name }) {
  const hero = HEROICON_SRCS[name];
  if (hero) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
        className="svg-icon"
        dangerouslySetInnerHTML={{ __html: svgBody(hero) }}
      />
    );
  }
  const filled = name === "github";
  return (
    <svg
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth="1.5"
      aria-hidden="true"
      className={"svg-icon" + (name === "github" ? " github" : "")}
    >
      <path d={CUSTOM_PATHS[name]} />
    </svg>
  );
}