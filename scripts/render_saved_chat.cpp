// Offline reconstruction through the exact installed llama.cpp server parser.
// Loads vocabulary only. Never creates an inference context or calls decode.
#include "arg.h"
#include "chat.h"
#include "llama.h"
#include "server-common.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

static json read_json(const fs::path & path) {
    std::ifstream file(path);
    if (!file) throw std::runtime_error("missing input file");
    return json::parse(std::string(std::istreambuf_iterator<char>(file), {}));
}

static void write_new(const fs::path & path, const json & value) {
    if (fs::exists(path)) throw std::runtime_error("refuse output overwrite");
    std::ofstream file(path);
    if (!file) throw std::runtime_error("cannot create output file");
    file << value.dump(2) << '\n';
    if (!file) throw std::runtime_error("incomplete output write");
}

int main(int argc, char ** argv) {
    try {
        if (argc != 2) throw std::runtime_error("one private batch manifest required");
        const auto manifest = read_json(argv[1]);
        if (manifest.at("cases").size() != 69) throw std::runtime_error("fixed 69 renderings required");
        std::vector<std::string> command = manifest.at("recorded_server_command").get<std::vector<std::string>>();
        std::vector<char *> args;
        for (auto & item : command) args.push_back(item.data());
        common_params params;
        if (!common_params_parse(int(args.size()), args.data(), params, LLAMA_EXAMPLE_SERVER)) {
            throw std::runtime_error("recorded command did not parse");
        }
        if (!params.use_jinja || !params.chat_template.empty() || !params.media_path.empty()) {
            throw std::runtime_error("unexpected template or media override");
        }
        auto model_params = llama_model_default_params();
        model_params.vocab_only = true;
        model_params.load_mode = LLAMA_LOAD_MODE_NONE;
        model_params.n_gpu_layers = 0;
        const auto model_path = manifest.at("model_path").get<std::string>();
        std::unique_ptr<llama_model, decltype(&llama_model_free)> model(
            llama_model_load_from_file(model_path.c_str(), model_params), llama_model_free);
        if (!model) throw std::runtime_error("vocabulary load failed");
        auto templates = common_chat_templates_init(model.get(), "");
        const bool thinking = params.enable_reasoning != 0 &&
            common_chat_templates_support_enable_thinking(templates.get());
        server_chat_params options{
            params.use_jinja, params.prefill_assistant, params.reasoning_format,
            params.default_template_kwargs, std::move(templates), false, false, false,
            thinking, params.sampling.reasoning_budget_tokens,
            params.sampling.reasoning_budget_message, params.media_path, params.force_pure_content_parser,
        };
        const auto vocab = llama_model_get_vocab(model.get());
        const fs::path output = manifest.at("output_dir").get<std::string>();
        if (!fs::is_directory(output)) throw std::runtime_error("output directory not prepared");
        json metadata{
            {"vocabulary_only", true}, {"inference_contexts_created", 0}, {"decode_calls", 0},
            {"default_template", common_chat_templates_source(options.tmpls.get(), "")},
            {"tool_template", common_chat_templates_source(options.tmpls.get(), "tool_use")},
            {"enable_thinking", thinking}, {"prefill_assistant", params.prefill_assistant},
            {"reasoning_format", common_reasoning_format_name(params.reasoning_format)},
            {"default_template_kwargs", params.default_template_kwargs},
        };
        write_new(output / "renderer_metadata_private.json", metadata);
        for (const auto & entry : manifest.at("cases")) {
            const auto name = entry.at("id").get<std::string>();
            if (name.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_") != std::string::npos) {
                throw std::runtime_error("invalid case identifier");
            }
            write_new(output / (name + "_started.json"), json{{"id", name}, {"status", "rendering_started"}});
            auto body = read_json(entry.at("request_path").get<std::string>());
            for (const auto & message : body.at("messages")) {
                if (message.contains("content") && !message.at("content").is_string() && !message.at("content").is_null()) {
                    throw std::runtime_error("only plain-text recorded messages are allowed");
                }
            }
            std::vector<raw_buffer> files;
            common_chat_session session;
            auto parsed = oaicompat_chat_params_parse(vocab, body, options, files, session);
            if (!files.empty() || !parsed.at("prompt").is_string()) throw std::runtime_error("unexpected media or prompt type");
            const auto tokens = tokenize_mixed(vocab, parsed.at("prompt"), true, true);
            common_params_sampling sampling;
            session.apply_sampling(sampling);
            json triggers = json::array();
            for (const auto & trigger : sampling.grammar_triggers) {
                triggers.push_back(json{{"type", int(trigger.type)}, {"value", trigger.value}, {"token", trigger.token}});
            }
            json preserved = json::array();
            for (const auto token : sampling.preserved_tokens) preserved.push_back(token);
            json controls{
                {"format", common_chat_format_name(session.format())},
                {"grammar", session.grammar()}, {"grammar_lazy", sampling.grammar_lazy},
                {"grammar_triggers", triggers}, {"preserved_tokens", preserved},
                {"generation_prompt", session.generation_prompt()},
                {"thinking_start_tag", session.thinking_start_tag()},
                {"thinking_end_tags", session.thinking_end_tags()},
                {"additional_stops", session.additional_stops()},
            };
            parsed.erase("prompt");
            // These source fields remain available in the original request. They
            // are not used to decide equality of the separately rendered prompt.
            parsed.erase("messages");
            json result{
                {"id", name}, {"prompt", session.prompt().str()}, {"tokens", tokens},
                {"input_tokens", tokens.size()}, {"session_controls", controls},
                {"parsed_non_message_parameters", parsed}, {"media_files", files.size()},
            };
            write_new(output / (name + "_rendered_private.json"), result);
        }
        write_new(output / "renderer_complete.json", json{{"renderings", 69}, {"decode_calls", 0}});
        return 0;
    } catch (const std::exception & error) {
        // The parent redirects this to the private batch log, never a public report.
        std::cerr << error.what() << '\n';
        return 1;
    }
}
