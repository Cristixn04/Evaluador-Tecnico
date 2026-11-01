"use client";

import * as React from "react";

export type ToastVariant = "default" | "destructive" | "success";

export interface ToastItem {
  id: string;
  title?: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

type Action =
  | { type: "ADD_TOAST"; toast: ToastItem }
  | { type: "DISMISS_TOAST"; toastId: string }
  | { type: "REMOVE_TOAST"; toastId: string };

interface State {
  toasts: ToastItem[];
}

const TOAST_LIMIT = 5;
const TOAST_REMOVE_DELAY = 1000;

let count = 0;
function genId() {
  count = (count + 1) % Number.MAX_SAFE_INTEGER;
  return `toast-${count}-${Date.now().toString(36)}`;
}

const toastTimeouts = new Map<string, ReturnType<typeof setTimeout>>();

const listeners: Array<(state: State) => void> = [];
let memoryState: State = { toasts: [] };

function dispatch(action: Action) {
  memoryState = reducer(memoryState, action);
  listeners.forEach((listener) => {
    listener(memoryState);
  });
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "ADD_TOAST":
      return {
        ...state,
        toasts: [action.toast, ...state.toasts].slice(0, TOAST_LIMIT),
      };

    case "DISMISS_TOAST": {
      const { toastId } = action;

      // Programar borrado final tras animación de salida
      if (!toastTimeouts.has(toastId)) {
        const timeout = setTimeout(() => {
          toastTimeouts.delete(toastId);
          dispatch({ type: "REMOVE_TOAST", toastId });
        }, TOAST_REMOVE_DELAY);
        toastTimeouts.set(toastId, timeout);
      }

      return {
        ...state,
        toasts: state.toasts.filter((t) => t.id !== toastId),
      };
    }

    case "REMOVE_TOAST":
      return {
        ...state,
        toasts: state.toasts.filter((t) => t.id !== action.toastId),
      };
  }
}

export function toast(props: Omit<ToastItem, "id">) {
  const id = genId();

  const update = (props: Partial<ToastItem>) => {
    // Para actualizaciones si fuera necesario
  };

  const dismiss = () => dispatch({ type: "DISMISS_TOAST", toastId: id });

  dispatch({
    type: "ADD_TOAST",
    toast: {
      ...props,
      id,
    },
  });

  const duration = props.duration ?? 4000;
  if (duration > 0) {
    setTimeout(() => {
      dismiss();
    }, duration);
  }

  return {
    id,
    dismiss,
    update,
  };
}

export function useToast() {
  const [state, setState] = React.useState<State>(memoryState);

  React.useEffect(() => {
    listeners.push(setState);
    return () => {
      const index = listeners.indexOf(setState);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    };
  }, [state]);

  return {
    ...state,
    toast,
    dismiss: (toastId: string) => dispatch({ type: "DISMISS_TOAST", toastId }),
  };
}
