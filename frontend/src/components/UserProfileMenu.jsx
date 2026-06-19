import { useEffect, useRef, useState } from 'react';
import LogOutIcon from './LogOutIcon';
import ProfileIcon from './ProfileIcon';

const UserProfileMenu = ({ email, onSignOut }) => {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    const handlePointerDown = (event) => {
      if (!menuRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const handleSignOut = () => {
    setOpen(false);
    onSignOut?.();
  };

  return (
    <div className="relative shrink-0" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Profile menu"
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-600 sm:h-9 sm:w-9"
      >
        <ProfileIcon className="h-4 w-4 sm:h-[18px] sm:w-[18px]" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+0.375rem)] z-50 w-56 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
        >
          {email && (
            <div className="border-b border-slate-100 px-3 py-2.5">
              <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Signed in as</p>
              <p className="mt-0.5 truncate text-sm font-medium text-slate-700" title={email}>
                {email}
              </p>
            </div>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={handleSignOut}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-600 transition hover:bg-rose-50 hover:text-rose-600"
          >
            <LogOutIcon className="h-4 w-4 shrink-0" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
};

export default UserProfileMenu;
