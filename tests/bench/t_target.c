/* 通用性靶场：一个小程序，三处"真值"都是**构造出来的**，不依赖任何游戏
 *
 *   1 结构表：实体数组，名字 + 花费 + 冷却（步长 24）
 *   2 分档开关：switch(k) 返回 25 / 15 / 50
 *   3 浮点常量：static const double 400.0，被算进输出
 *
 * 程序在 stdout 打一行 JSON：cost_sum / case4 / case5 / cd
 * 验收脚本改一个字节再看这几个数变没变 —— 行为验证，不猜地址。
 */
#include <stdio.h>
#include <stdlib.h>

typedef struct {
    const char *name;
    int cost;            /* 表真值：跨行同一列 */
    int cooldown;
    int pad;
} Entity;

static volatile const Entity ENTITIES[] = {
    {"ALPHA", 25, 150, 1},
    {"BETA", 50, 75, 2},
    {"GAMMA", 75, 37, 3},
    {"DELTA", 100, 25, 4},
};

static volatile double COOLDOWN_BASE = 400.0;  /* 浮点真值：volatile 防止被常量折叠 */

static int cost_sum(void)
{
    int s = 0;
    unsigned i;
    for (i = 0; i < sizeof(ENTITIES) / sizeof(ENTITIES[0]); i++)
        s += ENTITIES[i].cost;               /* 基址 + i*步长 的引用 */
    return s;
}

static int classify(int k)
{
    switch (k) {
    case 4:  return 25;                      /* 分档真值（case4） */
    case 5:  return 15;                      /* 分档真值（case5，用 15->30 来考） */
    case 6:  return 50;
    default: return 0;
    }
}

static double cooldown(void)
{
    return COOLDOWN_BASE / 4.0;
}

int main(void)
{
    printf("{\"cost_sum\":%d,\"case4\":%d,\"case5\":%d,\"cd\":%.1f}\n",
           cost_sum(), classify(4), classify(5), cooldown());
    return 0;
}
