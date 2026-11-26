// A small uGUI screen built at start: a score button, a name field, the texts they change. x86Sim reads it through its
// Unity reader (IL2CPP object model) and drives it through MCP (tests/ax/games_e2e.py's unity check).
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

public class Game : MonoBehaviour
{
    int score;
    Text scoreText, nameText;
    Font font;

    void Start()
    {
        font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        Camera.main.backgroundColor = new Color(0.12f, 0.14f, 0.2f);
        new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
        var canvasGo = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        canvasGo.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
        var scaler = canvasGo.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(402, 874);
        var root = canvasGo.transform;

        MakeText(root, "Title", "Unity on x86Sim", 34, 300);
        scoreText = MakeText(root, "Score", "Score: 0", 28, 200);

        var play = MakeBox(root, "Play", new Color(0.3f, 0.6f, 0.9f), 100, new Vector2(220, 70));
        var button = play.AddComponent<Button>();
        MakeText(play.transform, "Text", "Play", 28, 0);
        button.onClick.AddListener(() => { score++; scoreText.text = "Score: " + score; });

        var nameGo = MakeBox(root, "Name", Color.white, -20, new Vector2(300, 60));
        var field = nameGo.AddComponent<InputField>();
        var placeholder = MakeText(nameGo.transform, "Placeholder", "Your name", 24, 0);
        placeholder.color = new Color(0.5f, 0.5f, 0.5f);
        var typed = MakeText(nameGo.transform, "Text", "", 24, 0);
        typed.color = Color.black;
        typed.supportRichText = false;
        field.textComponent = typed;
        field.placeholder = placeholder;
        nameText = MakeText(root, "NameEcho", "Name: ", 24, -120);
        field.onValueChanged.AddListener(v => nameText.text = "Name: " + v);
    }

    GameObject MakeBox(Transform parent, string name, Color color, float y, Vector2 size)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(Image));
        go.transform.SetParent(parent, false);
        var rt = go.GetComponent<RectTransform>();
        rt.sizeDelta = size;
        rt.anchoredPosition = new Vector2(0, y);
        go.GetComponent<Image>().color = color;
        return go;
    }

    Text MakeText(Transform parent, string name, string value, int size, float y)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(Text));
        go.transform.SetParent(parent, false);
        var rt = go.GetComponent<RectTransform>();
        rt.sizeDelta = new Vector2(380, size * 2);
        rt.anchoredPosition = new Vector2(0, y);
        var t = go.GetComponent<Text>();
        t.font = font;
        t.fontSize = size;
        t.alignment = TextAnchor.MiddleCenter;
        t.text = value;
        t.color = Color.white;
        return t;
    }
}
