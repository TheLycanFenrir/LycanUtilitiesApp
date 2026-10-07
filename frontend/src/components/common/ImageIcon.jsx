export function ImgIcon({ src, alt = "", className = "" }) {
  return (
    <div className={`icon-img-wrapper ${className}`}>
      <img src={src} alt={alt} className="icon-img" />
    </div>
  );
}