import { StoreProvider, useStore } from "./state/store";
import Sidebar from "./components/Sidebar";
import Onboarding from "./screens/Onboarding";
import NichePicker from "./screens/NichePicker";
import NewVideo from "./screens/NewVideo";
import ProjectView from "./screens/ProjectView";
import Schedule from "./screens/Schedule";
import Settings from "./screens/Settings";
import Library from "./screens/Library";
import Activate from "./screens/Activate";
import UpdateBanner from "./components/UpdateBanner";

function Screen() {
  const { state } = useStore();
  const r = state.route;
  switch (r.name) {
    case "onboarding": return <Onboarding />;
    case "niche": return <NichePicker />;
    case "new": return <NewVideo key={r.dir ?? r.niche} niche={r.niche} dir={r.dir} />;
    case "project": return <ProjectView key={r.dir} dir={r.dir} />;
    case "settings": return <Settings key={r.tab ?? "gen"} />;
    case "schedule": return <Schedule />;
    case "library": return <Library />;
    case "activate": return null;
  }
}

function Shell() {
  const { state, boot } = useStore();
  if (!state.ready) return null;
  if (state.route.name === "activate") return <Activate reason={state.route.reason} onDone={() => void boot()} />;
  return (
    <div className="app">
      <UpdateBanner />
      <div className="body">
        <Sidebar />
        <main className="main"><Screen /></main>
      </div>
      <div className={"toast" + (state.toast ? " on" : "")} role="status">{state.toast}</div>
    </div>
  );
}

export default function App() {
  return <StoreProvider><Shell /></StoreProvider>;
}
