export default function PromptSuggestions() {
  return (
    <div className="space-y-3">
      <button className="bg-white/60 hover:bg-white border border-gray-200 px-4 py-2 rounded-full text-sm shadow-sm backdrop-blur">
        What can I ask you to do?
      </button>
      <br />
      <button className="bg-white/60 hover:bg-white border border-gray-200 px-4 py-2 rounded-full text-sm shadow-sm backdrop-blur">
        What projects should I be concerned about right now?
      </button>
    </div>
  )
}
