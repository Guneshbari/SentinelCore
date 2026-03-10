import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import GlobalFilterBar from './GlobalFilterBar';

export default function DashboardLayout() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <Sidebar />
      <Topbar />
      <GlobalFilterBar />
      <main className="ml-[220px] mt-[96px] p-6">
        <Outlet />
      </main>
    </div>
  );
}
