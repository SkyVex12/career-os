"use client";

import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { api } from "../lib/api";
import Topbar from "../components/Topbar";
import { useScope } from "../components/ClientShell";

import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
} from "@dnd-kit/core";

function userLabel(u) {
  return (
    u.name ||
    `${u.firstname || ""} ${u.lastname || ""}`.trim() ||
    u.email ||
    u.id
  );
}

function DroppableColumn({ id, title, count, children }) {
  const { setNodeRef, isOver } = useDroppable({ id });

  return (
    <div
      ref={setNodeRef}
      className="card"
      style={{
        border: isOver ? "1px solid rgba(255,255,255,0.25)" : undefined,
        boxShadow: isOver
          ? "0 0 0 2px rgba(255,255,255,0.08) inset"
          : undefined,
      }}
    >
      <div className="cardTitle">{title}</div>
      <div className="muted" style={{ marginBottom: 10 }}>
        Total: {count}
      </div>
      <div className="list">{children}</div>
    </div>
  );
}

function DraggableUserRow({ u }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: u.id,
      data: { user: u },
    });

  const style = {
    transform: transform
      ? `translate3d(${transform.x}px, ${transform.y}px, 0)`
      : undefined,
    opacity: isDragging ? 0.6 : 1,
    cursor: "grab",
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="listRow"
      {...listeners}
      {...attributes}
    >
      <div>
        <div style={{ fontWeight: 700 }}>{userLabel(u)}</div>
        <div className="muted">
          {u.id}
          {u.email ? ` • ${u.email}` : ""}
        </div>
      </div>
    </div>
  );
}

export default function ManageUsersPage() {
  const { mounted, principal } = useScope();

  // linked users (your “manage space”) — currently stored in items
  const [items, setItems] = useState([]);
  // all users (global pool)
  const [allUsers, setAllUsers] = useState([]);

  const [status, setStatus] = useState("");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstname, setFirstname] = useState("");
  const [lastname, setLastname] = useState("");
  const [dob, setDob] = useState("");

  const [query, setQuery] = useState("");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  async function refreshLinked() {
    const res = await api("/v1/users");
    const list = Array.isArray(res) ? res : res.items || [];
    setItems(list);
  }

  async function refreshAll() {
    const res = await api("/v1/admin/users/all");
    const list = Array.isArray(res) ? res : res.items || [];
    setAllUsers(list);
  }

  async function refresh() {
    await Promise.all([refreshLinked(), refreshAll()]);
  }

  useEffect(() => {
    if (!mounted) return;
    refresh().catch((e) => setStatus(String(e?.message || e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted]);

  async function onCreate(e) {
    e.preventDefault();
    const loadingId = toast.loading("Creating user...");
    try {
      await api("/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({ email, password, firstname, lastname, dob }),
      });
      setEmail("");
      setPassword("");
      setFirstname("");
      setLastname("");
      setDob("");
      toast.success("User created & linked", { id: loadingId });
      await refresh();
    } catch (e) {
      toast.error(e?.message || "Create failed", { id: loadingId });
    }
  }

  // derive available (unlinked) users from allUsers - items
  const linkedIdSet = useMemo(() => new Set(items.map((u) => u.id)), [items]);

  const availableUsers = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allUsers
      .filter((u) => !linkedIdSet.has(u.id))
      .filter((u) => {
        if (!q) return true;
        const hay = `${u.id} ${u.email || ""} ${u.firstname || ""} ${
          u.lastname || ""
        } ${u.name || ""}`.toLowerCase();
        return hay.includes(q);
      });
  }, [allUsers, linkedIdSet, query]);

  async function linkUser(userId) {
    await api("/v1/admin/users/link", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  }

  async function unlinkUser(userId) {
    await api("/v1/admin/users/unlink", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  }

  async function onDragEnd(evt) {
    const activeId = String(evt.active?.id || "");
    const overId = evt.over?.id ? String(evt.over.id) : null;
    if (!activeId || !overId) return;

    // We only drop onto columns: "all" or "linked"
    if (overId !== "all" && overId !== "linked") return;

    const isInLinked = linkedIdSet.has(activeId);
    const target = overId; // "all" | "linked"

    // no-op
    if (
      (isInLinked && target === "linked") ||
      (!isInLinked && target === "all")
    )
      return;

    // optimistic UI update + rollback on failure
    const prevLinked = items;

    try {
      if (target === "linked") {
        const u = allUsers.find((x) => x.id === activeId);
        if (u) setItems((prev) => [u, ...prev]);
        await linkUser(activeId);
        toast.success("Success to Link user");
      } else {
        setItems((prev) => prev.filter((u) => u.id !== activeId));
        await unlinkUser(activeId);
        toast.success("Success to Unlink user");
      }
    } catch (e) {
      setItems(prevLinked);
      toast.error(String(e?.message || e));
    }
  }

  if (!mounted) return null;

  if (!principal) {
    return (
      <main className="container">
        <Topbar title="Manage Users" subtitle="Admin only" />
        <div className="card">Please login.</div>
      </main>
    );
  }

  if (principal.type !== "admin") {
    return (
      <main className="container">
        <Topbar title="Manage Users" subtitle="Admin only" />
        <div className="card" style={{ gap: 12, marginTop: 12 }}>
          Forbidden (admin only).
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <Topbar title="Manage Users" subtitle="Create & link users" />

      <div className="grid2" style={{ gap: 12, marginTop: 12 }}>
        <div className="card">
          <div className="cardTitle">Create new user</div>
          <form onSubmit={onCreate}>
            <label className="label">Email</label>
            <input
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />

            <label className="label">Password</label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />

            <div className="row">
              <div>
                <label className="label">First name</label>
                <input
                  className="input"
                  value={firstname}
                  onChange={(e) => setFirstname(e.target.value)}
                />
              </div>
              <div>
                <label className="label">Last name</label>
                <input
                  className="input"
                  value={lastname}
                  onChange={(e) => setLastname(e.target.value)}
                />
              </div>
            </div>

            <div className="row">
              <label className="label">Date of birth</label>
              <input
                className="input"
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
              />

              <button className="pill pillBtn" type="submit">
                Create & Link
              </button>
            </div>

            {status ? <div className="status">{status}</div> : null}
          </form>
        </div>

        <div
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}
        >
          <div
            className="card"
            style={{ gridColumn: "1 / -1", paddingBottom: 0 }}
          >
            <div className="row" style={{ alignItems: "center", gap: 12 }}>
              <div className="muted">
                Drag users between columns to link/unlink.
              </div>
              <input
                className="input"
                placeholder="Search all users…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ maxWidth: 320, marginLeft: "auto" }}
              />
            </div>
          </div>

          <DndContext sensors={sensors} onDragEnd={onDragEnd}>
            <DroppableColumn
              id="all"
              title="All users"
              count={availableUsers.length}
            >
              {availableUsers.map((u) => (
                <DraggableUserRow key={u.id} u={u} />
              ))}
              {!availableUsers.length ? (
                <div className="muted">No available users.</div>
              ) : null}
            </DroppableColumn>

            <DroppableColumn
              id="linked"
              title="My linked users"
              count={items.length}
            >
              {items.map((u) => (
                <DraggableUserRow key={u.id} u={u} />
              ))}
              {!items.length ? (
                <div className="muted">No users linked yet.</div>
              ) : null}
            </DroppableColumn>
          </DndContext>
        </div>
      </div>
    </main>
  );
}
