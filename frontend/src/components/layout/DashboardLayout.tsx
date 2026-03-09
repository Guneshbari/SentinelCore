import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function DashboardLayout() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <Sidebar />
      <Topbar />
      <main className="ml-[220px] mt-[56px] p-6">
        <Outlet />
      </main>
    </div>
  );
}
