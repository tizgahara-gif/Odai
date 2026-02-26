using Microsoft.UI.Xaml;
using System;

namespace SilhouetteLocalDaily;

public sealed partial class MainWindow : Window
{
    private static readonly string[] Silhouettes =
    {
        "直線＋欠け",
        "大円弧＋垂下",
        "S字長物＋薄膜",
        "点群外周"
    };

    private static readonly string[] LocalRules =
    {
        "分節",
        "孔群",
        "張力線",
        "サイズグラデ鱗/棘"
    };

    private readonly Random _random = new();

    public MainWindow()
    {
        InitializeComponent();
        TodayTextBlock.Text = $"Today: {DateTime.Now:yyyy-MM-dd}";
        GenerateTheme();
    }

    private void OnGenerateClicked(object sender, RoutedEventArgs e)
    {
        GenerateTheme();
    }

    private void GenerateTheme()
    {
        var silhouette = Silhouettes[_random.Next(Silhouettes.Length)];
        var localRule = LocalRules[_random.Next(LocalRules.Length)];

        SilhouetteTextBlock.Text = $"Silhouette: {silhouette}";
        LocalRuleTextBlock.Text = $"Local Rule: {localRule}";
    }
}
