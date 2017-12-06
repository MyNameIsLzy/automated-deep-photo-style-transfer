import argparse
import os

import numpy as np
import tensorflow as tf
from PIL import Image

from vgg19 import VGG19ConvSub, load_weights, VGG_MEAN


def style_transfer(content_image, style_image, init_image, args):
    weight_restorer = load_weights(args.weights_data)

    image_placeholder = tf.placeholder(tf.float32, shape=[1, None, None, 3])
    vgg19 = VGG19ConvSub(image_placeholder)

    with tf.Session() as sess:
        transfer_image = tf.Variable(init_image)

        sess.run(tf.global_variables_initializer())
        weight_restorer.init(sess)
        content_conv4_2 = sess.run(fetches=vgg19.conv4_2, feed_dict={image_placeholder: content_image})
        style_conv1_1, style_conv2_1, style_conv3_1, style_conv4_1, style_conv5_1 = sess.run(
            fetches=[vgg19.conv1_1, vgg19.conv2_1, vgg19.conv3_1, vgg19.conv4_1, vgg19.conv5_1],
            feed_dict={image_placeholder: style_image})

        with tf.variable_scope("", reuse=True):
            vgg19 = VGG19ConvSub(transfer_image)

        content_loss = calculate_layer_content_loss(content_conv4_2, vgg19.conv4_2)

        style_loss = (1. / 5.) * calculate_layer_style_loss(style_conv1_1, vgg19.conv1_1)
        style_loss += (1. / 5.) * calculate_layer_style_loss(style_conv2_1, vgg19.conv2_1)
        style_loss += (1. / 5.) * calculate_layer_style_loss(style_conv3_1, vgg19.conv3_1)
        style_loss += (1. / 5.) * calculate_layer_style_loss(style_conv4_1, vgg19.conv4_1)
        style_loss += (1. / 5.) * calculate_layer_style_loss(style_conv5_1, vgg19.conv5_1)

        content_loss = args.content_weight * content_loss
        style_loss = args.style_weight * style_loss
        total_loss = content_loss + style_loss

        optimizer = tf.train.AdamOptimizer(learning_rate=args.adam_learning_rate, beta1=args.adam_beta1,
                                           beta2=args.adam_beta2, epsilon=args.adam_epsilon)
        train_op = optimizer.minimize(total_loss, var_list=[transfer_image])
        sess.run(adam_variables_initializer(optimizer, [transfer_image]))

        min_loss, best_image = float("inf"), None
        for i in range(args.iterations + 1):
            _, result_image, loss, c_loss, s_loss = sess.run(
                fetches=[train_op, transfer_image, total_loss, content_loss, style_loss])

            if i % args.print_loss_interval == 0:
                print(
                    "Iteration: {0:5} \t Total loss: {1:15.2f} \t Content loss: {2:15.2f} \t Style loss: {3:15.2f}".format(
                        i, loss, c_loss, s_loss))

            if loss < min_loss:
                min_loss, best_image = loss, result_image

            if i % args.intermediate_result_interval == 0:
                save_image(best_image, "transfer/res_{}.png".format(i))

        return best_image


def adam_variables_initializer(adam_opt, var_list):
    adam_vars = [adam_opt.get_slot(var, name)
                 for name in adam_opt.get_slot_names()
                 for var in var_list if var is not None]
    adam_vars.extend(list(adam_opt._get_beta_accumulators()))
    return tf.variables_initializer(adam_vars)


def calculate_layer_content_loss(content_layer, transfer_layer):
    return tf.reduce_mean(tf.squared_difference(content_layer, transfer_layer))


def calculate_layer_style_loss(style_layer, transfer_layer):
    feature_map_count = np.float32(transfer_layer.shape[3].value)
    feature_map_size = np.float32(transfer_layer.shape[1].value) * np.float32(transfer_layer.shape[2].value)

    style_gram_matrix = calculate_gram_matrix(style_layer)
    transfer_gram_matrix = calculate_gram_matrix(transfer_layer)

    mean_square_error = tf.reduce_mean(tf.squared_difference(style_gram_matrix, transfer_gram_matrix))
    return mean_square_error / (4 * tf.square(feature_map_count) * tf.square(feature_map_size))


def calculate_gram_matrix(convolution_layer):
    matrix = tf.reshape(convolution_layer, shape=[-1, convolution_layer.shape[3]])
    return tf.matmul(matrix, matrix, transpose_a=True)


def load_image(filename):
    image = np.array(Image.open(filename).convert("RGB"), dtype=np.float32)
    image = image[:, :, ::-1] - VGG_MEAN
    image = image.reshape((1, image.shape[0], image.shape[1], 3)).astype(np.float32)
    return image


def save_image(image, filename):
    image = image[0, :, :, :] + VGG_MEAN
    image = image[:, :, ::-1]
    image = np.clip(image, 0, 255.0)
    image = np.uint8(image)

    result = Image.fromarray(image)
    result.save(filename)


if __name__ == "__main__":
    """Parse program arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--content_image_path", type=str, help="content image path", default="")
    parser.add_argument("--style_image_path", type=str, help="style image path", default="")
    parser.add_argument("--weights_data", type=str,
                        help="path to weights data (vgg19.npy). Download if file does not exist.", default="vgg19.npy")
    parser.add_argument("--output_image_path", type=str, help="Output image path, default: result.jpg",
                        default="result.jpg")
    parser.add_argument("--iterations", type=int, help="Number of iterations, default: 2000",
                        default=2000)
    parser.add_argument("--intermediate_result_interval", type=int,
                        help="Interval of iterations until a intermediate result is saved., default: 100",
                        default=100)
    parser.add_argument("--print_loss_interval", type=int,
                        help="Interval of iterations until the current loss is printed to console., default: 1",
                        default=1)
    parser.add_argument("--content_weight", type=float,
                        help="Weight of the content loss., default: 1e-3",
                        default=1e-3)
    parser.add_argument("--style_weight", type=float,
                        help="Weight of the style loss., default: 1",
                        default=1)
    parser.add_argument("--init_image_scaling", type=float,
                        help="Scaling factor for the init image (random noise)., default: 0.0001",
                        default=0.0001)
    parser.add_argument("--adam_learning_rate", type=float,
                        help="Learning rate for the adam optimizer., default: 1.0",
                        default=1.0)
    parser.add_argument("--adam_beta1", type=float,
                        help="Beta1 for the adam optimizer., default: 0.9",
                        default=0.9)
    parser.add_argument("--adam_beta2", type=float,
                        help="Beta2 for the adam optimizer., default: 0.999",
                        default=0.999)
    parser.add_argument("--adam_epsilon", type=float,
                        help="Epsilon for the adam optimizer., default: 1e-08",
                        default=1e-08)

    parser.add_argument("--gpu", help="comma separated list of GPU(s) to use.", default="0")
    args = parser.parse_args()

    if args.gpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

    args = parser.parse_args()

    """Check if image files exist"""
    for path in [args.content_image_path, args.style_image_path]:
        if path is None or not os.path.isfile(path):
            print("Image file %s does not exist." % path)
            exit(0)

    # create directory transfer if it does not exist
    if not os.path.exists("transfer"):
        os.makedirs("transfer")

    content_image = load_image(args.content_image_path)
    style_image = load_image(args.style_image_path)
    init_image = np.random.randn(*content_image.shape).astype(np.float32) * args.init_image_scaling
    result = style_transfer(content_image, style_image, init_image, args)
    save_image(result, "final_transfer_image.png")
