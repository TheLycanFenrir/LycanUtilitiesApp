import { createContext, useContext, useEffect, useMemo } from "react";
import { useSyncExternalStore } from "react";
import {
  subscribeForm, getFormSnapshot, initForm, clearForm,
  setFieldValue, getFieldValue, getAllValues, setAllValues,
  resetDefaults as resetFieldDefaults, addField, deleteField,
  hideField, unhideField, setFocus as requestFocus, setFieldStatus,
  registerGlobalBridge,
} from "../utils/form/formStore.js";

const FormStateContext = createContext(null);

/**
 * Owns the external form store for one active module. The store is
 * initialized once per (moduleId, schema fingerprint); dynamic field APIs
 * (add_field / delete_field) mutate the store directly and are never
 * clobbered by this provider's initialization. Unmount clears the store.
 */
export function FormStateProvider({ moduleId, fieldsKey, fields, children }) {
  const snapshot = useSyncExternalStore(subscribeForm, getFormSnapshot);

  useEffect(() => {
    registerGlobalBridge();
    initForm(moduleId, fields);
    return () => clearForm();
  }, [moduleId, fieldsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(
    () => ({
      moduleId,
      schema: fields,
      snapshot,
      setValue: (id, v, opts) => setFieldValue(id, v, opts),
      getValue: getFieldValue,
      getAll: getAllValues,
      setAll: setAllValues,
      reset: resetFieldDefaults,
      addField,
      deleteField,
      hideField,
      unhideField,
      setFocus: requestFocus,
      setFieldStatus,
    }),
    [moduleId, fields, snapshot],
  );

  return <FormStateContext.Provider value={value}>{children}</FormStateContext.Provider>;
}

export function useFormState() {
  const ctx = useContext(FormStateContext);
  if (!ctx) {
    throw new Error("useFormState must be used inside <FormStateProvider>");
  }
  return ctx;
}