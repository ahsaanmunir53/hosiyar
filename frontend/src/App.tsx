import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router-dom";
import Header from "./components/Header";
import { useLang } from "./i18n";
import CheckPage from "./pages/CheckPage";
import HowPage from "./pages/HowPage";
import TrendsPage from "./pages/TrendsPage";

// Pages most visitors never open are loaded on demand.
const ToolsPage = lazy(() => import("./pages/ToolsPage"));
const QuizPage = lazy(() => import("./pages/QuizPage"));
const QualityPage = lazy(() => import("./pages/QualityPage"));
const PrivacyPage = lazy(() => import("./pages/PrivacyPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const SharePage = lazy(() => import("./pages/SharePage"));

export default function App() {
  const { t } = useLang();
  return (
    <div className="app">
      <a className="skip" href="#content">
        Skip to content
      </a>
      <Header />
      <div id="content">
        <Suspense fallback={<p className="muted page">{t("loading")}</p>}>
          <Routes>
            <Route path="/" element={<CheckPage />} />
            <Route path="/share" element={<SharePage />} />
            <Route path="/tools" element={<ToolsPage />} />
            <Route path="/trends" element={<TrendsPage />} />
            <Route path="/quiz" element={<QuizPage />} />
            <Route path="/how" element={<HowPage />} />
            <Route path="/quality" element={<QualityPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="*" element={<CheckPage />} />
          </Routes>
        </Suspense>
      </div>
      <footer className="sitefoot">
        <p>{t("footer")}</p>
        <nav className="sitefoot__links" aria-label="More">
          <Link to="/quality">{t("foot_quality")}</Link>
          <Link to="/privacy">{t("foot_privacy")}</Link>
          <Link to="/tools#install">{t("install_title")}</Link>
          <Link to="/admin">{t("foot_admin")}</Link>
        </nav>
      </footer>
    </div>
  );
}
