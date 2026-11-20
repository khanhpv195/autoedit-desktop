export default function VideoPlayer({ src, small }: { src: string; small?: boolean }) {
  return <video key={src} className={"vid" + (small ? " small" : "")} src={src} controls playsInline />;
}
