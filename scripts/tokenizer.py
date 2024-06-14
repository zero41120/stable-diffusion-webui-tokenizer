import html
from modules import script_callbacks, shared

import gradio as gr


css = """
.tokenizer-token{
    opacity: 0.8;
    cursor: pointer;
    --body-text-color: #000;
}
.tokenizer-token:hover {opacity: 1;}
.tokenizer-token-0 {background: var(--primary-300);}
.tokenizer-token-1 {background: var(--primary-400);}
.tokenizer-token-2 {background: var(--primary-500);}
.tokenizer-token-3 {background: var(--primary-600);}
"""


class VanillaClip:
    def __init__(self, clip):
        self.clip = clip
        assert hasattr(self.clip, "tokenizer"), "VanillaClip requires 'tokenizer' attribute"
        assert hasattr(self.clip.tokenizer, "get_vocab"), "Tokenizer must have 'get_vocab'"
        assert hasattr(self.clip.tokenizer, "byte_decoder"), "Tokenizer must have 'byte_decoder'"

    def vocab(self):
        return self.clip.tokenizer.get_vocab()

    def byte_decoder(self):
        return self.clip.tokenizer.byte_decoder

class OpenClip:
    def __init__(self, clip):
        self.clip = clip
        assert hasattr(self.clip, "tokenizer"), "OpenClip requires 'tokenizer' attribute"
        assert hasattr(self.clip.tokenizer, "_tokenizer"), "Tokenizer must have '_tokenizer'"
        self.tokenizer = self.clip.tokenizer._tokenizer

    def vocab(self):
        return self.tokenizer.encoder

    def byte_decoder(self):
        return self.tokenizer.byte_decoder

def initialize_clip_instance():
    base = shared.sd_model.cond_stage_model
    clip_candidates = [base.wrapped]
    # For SDXL, it is FrozenCLIPEmbedderForSDXLWithCustomWords and some others which are initalized in sd_hijack_clip.py in the embedders
    if hasattr(base, 'embedders'):
        for embedder in base.embedders:
            if hasattr(embedder, 'wrapped'):
                clip_candidates.append(embedder.wrapped)
    initializers = [VanillaClip, OpenClip]
    for clip in clip_candidates:
        for initializer in initializers:
            try:
                return initializer(clip)
            except AssertionError:
                continue
    raise RuntimeError('Failed to initialize a compatible CLIP instance from any candidate')

def tokenize(text, input_is_ids=False):
    clip = initialize_clip_instance()

    if input_is_ids:
        tokens = [int(x.strip()) for x in text.split(",")]
    else:
        tokens = shared.sd_model.cond_stage_model.tokenize([text])[0]

    vocab = {v: k for k, v in clip.vocab().items()}

    code = ''
    ids = []

    current_ids = []
    class_index = 0

    byte_decoder = clip.byte_decoder()

    def dump(last=False):
        nonlocal code, ids, current_ids

        words = [vocab.get(x, "") for x in current_ids]

        def wordscode(ids, word):
            nonlocal class_index
            res = f"""<span class='tokenizer-token tokenizer-token-{class_index%4}' title='{html.escape(", ".join([str(x) for x in ids]))}'>{html.escape(word)}</span>"""
            class_index += 1
            return res

        try:
            word = bytearray([byte_decoder[x] for x in ''.join(words)]).decode("utf-8")
        except UnicodeDecodeError:
            if last:
                word = "❌" * len(current_ids)
            elif len(current_ids) > 4:
                id = current_ids[0]
                ids += [id]
                local_ids = current_ids[1:]
                code += wordscode([id], "❌")

                current_ids = []
                for id in local_ids:
                    current_ids.append(id)
                    dump()

                return
            else:
                return

        word = word.replace("</w>", " ")

        code += wordscode(current_ids, word)
        ids += current_ids

        current_ids = []

    for token in tokens:
        token = int(token)
        current_ids.append(token)

        dump()

    dump(last=True)

    ids_html = f"""
<p>
Token count: {len(ids)}<br>
{", ".join([str(x) for x in ids])}
</p>
"""

    return code, ids_html


def add_tab():
    with gr.Blocks(analytics_enabled=False, css=css) as ui:
        gr.HTML(f"""
<style>{css}</style>
<p>
Before your text is sent to the neural network, it gets turned into numbers in a process called tokenization. These tokens are how the neural network reads and interprets text. Thanks to our great friends at Shousetsu愛 for inspiration for this feature.
</p>
""")

        with gr.Tabs() as tabs:
            with gr.Tab("Text input", id="input_text"):
                prompt = gr.Textbox(label="Prompt", elem_id="tokenizer_prompt", show_label=False, lines=8, placeholder="Prompt for tokenization")
                go = gr.Button(value="Tokenize", variant="primary")

            with gr.Tab("ID input", id="input_ids"):
                prompt_ids = gr.Textbox(label="Prompt", elem_id="tokenizer_prompt", show_label=False, lines=8, placeholder="Ids for tokenization (example: 9061, 631, 736)")
                go_ids = gr.Button(value="Tokenize", variant="primary")

        with gr.Tabs():
            with gr.Tab("Text"):
                tokenized_text = gr.HTML(elem_id="tokenized_text")

            with gr.Tab("Tokens"):
                tokens = gr.HTML(elem_id="tokenized_tokens")

        go.click(
            fn=tokenize,
            inputs=[prompt],
            outputs=[tokenized_text, tokens],
        )

        go_ids.click(
            fn=lambda x: tokenize(x, input_is_ids=True),
            inputs=[prompt_ids],
            outputs=[tokenized_text, tokens],
        )

    return [(ui, "Tokenizer", "tokenizer")]


script_callbacks.on_ui_tabs(add_tab)
